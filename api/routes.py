from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from typing import Dict, Any, Tuple, Optional
from datetime import datetime
import os, re

from core.settings import HEYOO_PHONE_ID, HEYOO_TOKEN
from heyoo import WhatsApp

from models.schemas import ConversationState
from core.steps import (
    fill_from_text_modular,
    llm_parse_modular,
    advance_module,
    merge_state,
    summarize_patch_for_confirmation,
    MODULES,
    prompt_for_module,
)

router = APIRouter()
wa_client = WhatsApp(token=HEYOO_TOKEN, phone_number_id=HEYOO_PHONE_ID)

# Hardcodeá tu número acá
HARDCODED_USER_ID = "542616463629"

# ====== Memoria simple ======
_USER_STATE: Dict[str, ConversationState] = {}

def load_state(user_id: str) -> ConversationState:
    st = _USER_STATE.get(user_id)
    if st is None:
        st = ConversationState(user_id=user_id)
        st._handled_msg_ids = set()
        st._last_text = ""
        st._last_failed_module = None
        _USER_STATE[user_id] = st
    # compat
    if not hasattr(st, "_handled_msg_ids"):
        st._handled_msg_ids = set()
    if not hasattr(st, "_last_text"):
        st._last_text = ""
    if not hasattr(st, "_last_failed_module"):
        st._last_failed_module = None
    if not hasattr(st, "module_idx") or st.module_idx is None:
        st.module_idx = 0
    return st

def save_state(state: ConversationState):
    state.updated_at = datetime.utcnow()
    _USER_STATE[state.user_id] = state

# ====== Helpers ======
def _extract_incoming(payload: Dict[str, Any]) -> Tuple[str, Optional[str]]:
    try:
        entry = payload.get("entry", [])[0]
        change = entry.get("changes", [])[0]
        value = change.get("value", {})

        if value.get("statuses"):
            return "__IGNORE__", None

        msgs = value.get("messages") or []
        if msgs:
            msg = msgs[0]
            msg_type = msg.get("type")
            msg_id = msg.get("id")
            if msg_type == "text":
                body = (msg.get("text", {}) or {}).get("body", "") or ""
                return body, msg_id
            else:
                return "__IGNORE__", msg_id
    except Exception:
        pass

    text = payload.get("text") or payload.get("message") or payload.get("body") or ""
    mid = payload.get("message_id")
    if not text:
        return "__IGNORE__", mid
    return text, mid

# ====== Core TRIAGE ======
def _triage_block(state: ConversationState, text: str) -> Tuple[Optional[list[str]], ConversationState]:
    module_idx = state.module_idx

    # 1) Parser local
    patch_local = fill_from_text_modular(state, module_idx, text or "")
    if patch_local:
        state = merge_state(state, {"ficha": patch_local.get("ficha", patch_local)})

    # 2) Parser LLM (si el módulo lo usa) — acá podrías normalizar motivo con LLM
    patch_llm: Dict[str, Any] = {}
    if 0 <= module_idx < len(MODULES) and MODULES[module_idx].get("use_llm"):
        # Si querés activar la normalización del motivo vía LLM, implementalo en steps.llm_parse_modular
        patch_llm = llm_parse_modular(text or "", module_idx) or {}
        if patch_llm:
            state = merge_state(state, {"ficha": patch_llm.get("ficha", patch_llm)})

    # 3) Confirmación combinada
    combined = {"ficha": {}}
    if patch_local:
        combined["ficha"].update(patch_local.get("ficha", patch_local))
    if patch_llm:
        combined["ficha"].update(patch_llm.get("ficha", patch_llm))

    had_any = bool(combined["ficha"])
    confirm = summarize_patch_for_confirmation(combined, module_idx) if had_any else "No pude extraer datos de este bloque."

    # 4) Lógica de avance
    start_only = (
        module_idx == 0
        and isinstance(combined.get("ficha"), dict)
        and set(combined["ficha"].keys()) == {"_start"}
    )
    advance_now = had_any and not start_only
    if advance_now:
        state.module_idx = min(state.module_idx + 1, len(MODULES) - 1)
        state._last_failed_module = None
    else:
        state._last_failed_module = None if start_only else module_idx

    # 5) Mensajes a enviar
    messages: list[str] = []

    if start_only:
        # Saludo en mensaje separado + prompt del módulo 0
        saludo = "Hola, vamos a completar tu ficha anestesiologica. Copia y pega el siguiente formato y rellenalo con tus datos."
        messages.append(saludo)
        messages.append(MODULES[0]["prompt"])
        return messages, state

    next_idx, next_prompt = advance_module(state)
    if next_idx is None:
        messages.append(f"{confirm} ¡Listo! Completamos todos los bloques.")
    else:
        # confirmación + prompt del módulo actual
        messages.append(confirm)
        messages.append(next_prompt)
        state.module_idx = next_idx

    return messages, state

# ====== HTTP ======
@router.post("/webhook")
async def webhook(req: Request):
    payload = await req.json()
    text, message_id = _extract_incoming(payload)

    if text == "__IGNORE__":
        return JSONResponse({"ok": True, "ignored": "non_text_or_status"})

    user_id = HARDCODED_USER_ID
    state = load_state(user_id)

    if message_id and message_id in state._handled_msg_ids:
        return JSONResponse({"ok": True, "ignored": "duplicate_message"})
    if message_id:
        state._handled_msg_ids.add(message_id)

    if text == state._last_text and state._last_failed_module == state.module_idx:
        return JSONResponse({"ok": True, "ignored": "same_text_same_module"})

    messages, state = _triage_block(state, text)
    save_state(state)
    state._last_text = text

    sent = []
    for msg in (messages or []):
        if not msg:
            continue
        try:
            wa_client.send_message(message=msg, recipient_id=user_id)
            sent.append(True)
        except Exception:
            sent.append(False)

    return JSONResponse({
        "to": user_id,
        "echo_text": text,
        "replies": messages,
        "sent": sent,
        "module": MODULES[state.module_idx]["name"] if 0 <= state.module_idx < len(MODULES) else None,
    })

@router.get("/health")
def health():
    return {"ok": True}
