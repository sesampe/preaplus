# routes.py
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from typing import Dict, Any, Tuple
from datetime import datetime

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

# Cliente WhatsApp
wa_client = WhatsApp(token=HEYOO_TOKEN, phone_number_id=HEYOO_PHONE_ID)

# Hardcodeá tu número acá
HARDCODED_USER_ID = "542616463629"

# ====== Almacenamiento en memoria ======
_USER_STATE: Dict[str, ConversationState] = {}

def load_state(user_id: str) -> ConversationState:
    st = _USER_STATE.get(user_id)
    if st is None:
        st = ConversationState(user_id=user_id)
        _USER_STATE[user_id] = st
    return st

def save_state(state: ConversationState):
    state.updated_at = datetime.utcnow()
    _USER_STATE[state.user_id] = state

# ====== Helpers ======

def _extract_text(payload: Dict[str, Any]) -> str:
    """
    Extrae texto de distintos formatos de webhook.
    Ignora eventos sin texto (p.ej., 'statuses' de WhatsApp Cloud).
    """
    # 1) Formato oficial Meta (WhatsApp Cloud)
    try:
        entry = payload.get("entry", [])[0]
        change = entry.get("changes", [])[0]
        value = change.get("value", {})

        # Si es un evento de status (entregado/leído), no hay que responder
        if value.get("statuses"):
            return "__IGNORE_STATUS_EVENT__"

        msgs = value.get("messages") or []
        if msgs:
            msg = msgs[0]
            if msg.get("type") == "text":
                return msg.get("text", {}).get("body", "") or ""
    except Exception:
        pass

    # 2) Variantes “compatibles” usadas en tests locales
    text = payload.get("text") or payload.get("message") or payload.get("body") or ""
    if not text and "messages" in payload:
        msgs = payload["messages"]
        if isinstance(msgs, list) and msgs:
            m0 = msgs[0]
            if isinstance(m0, dict) and "text" in m0:
                text = m0["text"].get("body", "") or ""
    return text or ""

# ====== Core TRIAGE ======
def _triage_block(state: ConversationState, text: str) -> Tuple[str, ConversationState]:
    module_idx = state.module_idx

    # 1) Patch local
    patch_local = fill_from_text_modular(state, module_idx, text or "")
    if patch_local:
        # merge_state acepta {"ficha": patch} o patch directo
        state = merge_state(state, {"ficha": patch_local.get("ficha", patch_local)})

    # 2) Patch LLM (si el módulo lo usa)
    patch_llm: Dict[str, Any] = {}
    if MODULES[module_idx]["use_llm"]:
        patch_llm = llm_parse_modular(text or "", module_idx) or {}
        if patch_llm:
            state = merge_state(state, {"ficha": patch_llm.get("ficha", patch_llm)})

    # 3) Confirmación usando el patch combinado (soporta shapes con/sin "ficha")
    combined = {"ficha": {}}
    if patch_local:
        combined["ficha"].update(patch_local.get("ficha", patch_local))
    if patch_llm:
        combined["ficha"].update(patch_llm.get("ficha", patch_llm))

    had_any = bool(combined["ficha"])
    confirm = (
        summarize_patch_for_confirmation(combined, module_idx)
        if had_any else "No pude extraer datos de este bloque."
    )

    # 4) Avance: solo si hubo algo que anotar
    if had_any:
        state.module_idx = min(state.module_idx + 1, len(MODULES) - 1)

    next_idx, next_prompt = advance_module(state)
    if next_idx is None:
        reply = f"{confirm} ¡Listo! Completamos todos los bloques."
    else:
        state.module_idx = next_idx
        reply = f"{confirm} {next_prompt}"
    return reply, state

# ====== HTTP ======
@router.post("/webhook")
async def webhook(req: Request):
    payload = await req.json()

    text = _extract_text(payload)

    # Ignorar eventos sin texto y eventos de status
    if text == "__IGNORE_STATUS_EVENT__":
        return JSONResponse({"ok": True, "ignored": "status_event"})
    if not text:
        return JSONResponse({"ok": True, "ignored": "no_text_message"})

    # Siempre usar el hardcode
    user_id = HARDCODED_USER_ID

    state = load_state(user_id)
    reply, state = _triage_block(state, text)
    save_state(state)

    # Enviar por WhatsApp
    try:
        wa_client.send_message(message=reply, recipient_id=user_id)
        sent = True
    except Exception:
        sent = False

    return JSONResponse({
        "to": user_id,
        "echo_text": text,
        "reply": reply,
        "sent": sent,
        "module": MODULES[state.module_idx]["name"],
    })

@router.get("/health")
def health():
    return {"ok": True}
