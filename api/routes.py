# api/routes.py
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from typing import Dict, Any, Tuple, Optional
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

wa_client = WhatsApp(token=HEYOO_TOKEN, phone_number_id=HEYOO_PHONE_ID)

# Hardcodeá tu número acá
HARDCODED_USER_ID = "542616463629"

# ====== Memoria simple ======
_USER_STATE: Dict[str, ConversationState] = {}

def load_state(user_id: str) -> ConversationState:
    st = _USER_STATE.get(user_id)
    if st is None:
        st = ConversationState(user_id=user_id)
        # Campos auxiliares para control de duplicados y spam
        st._handled_msg_ids = set()          # ids ya procesados (WhatsApp message.id)
        st._last_text = ""                    # último texto que vimos
        st._last_failed_module = None         # módulo en el que dijimos “No pude…” por última vez
        _USER_STATE[user_id] = st
    # compat si venís de un estado viejo
    if not hasattr(st, "_handled_msg_ids"):
        st._handled_msg_ids = set()
    if not hasattr(st, "_last_text"):
        st._last_text = ""
    if not hasattr(st, "_last_failed_module"):
        st._last_failed_module = None
    return st

def save_state(state: ConversationState):
    state.updated_at = datetime.utcnow()
    _USER_STATE[state.user_id] = state

# ====== Helpers ======

def _extract_incoming(payload: Dict[str, Any]) -> Tuple[str, Optional[str]]:
    """
    Devuelve (text, message_id) o ("__IGNORE__", None) si no hay que responder.
    - Ignora 'statuses' (entregado/leído).
    - Solo procesa mensajes de tipo 'text'.
    """
    try:
        entry = payload.get("entry", [])[0]
        change = entry.get("changes", [])[0]
        value = change.get("value", {})

        # 1) Eventos de status -> ignorar
        if value.get("statuses"):
            return "__IGNORE__", None

        # 2) Mensajes entrantes (solo text)
        msgs = value.get("messages") or []
        if msgs:
            msg = msgs[0]
            msg_type = msg.get("type")
            msg_id = msg.get("id")
            if msg_type == "text":
                body = (msg.get("text", {}) or {}).get("body", "") or ""
                return body, msg_id
            else:
                # otros tipos (image, button, interactive...) no los manejamos por ahora
                return "__IGNORE__", msg_id
    except Exception:
        pass

    # Variantes de test locales
    text = payload.get("text") or payload.get("message") or payload.get("body") or ""
    mid = payload.get("message_id")
    if not text:
        return "__IGNORE__", mid
    return text, mid

# ====== Core TRIAGE ======
def _triage_block(state: ConversationState, text: str) -> Tuple[Optional[str], ConversationState]:
    module_idx = state.module_idx

    # 1) Patch local
    patch_local = fill_from_text_modular(state, module_idx, text or "")
    if patch_local:
        state = merge_state(state, {"ficha": patch_local.get("ficha", patch_local)})

    # 2) Patch LLM (si el módulo lo usa)
    patch_llm: Dict[str, Any] = {}
    if 0 <= module_idx < len(MODULES) and MODULES[module_idx].get("use_llm"):
        patch_llm = llm_parse_modular(text or "", module_idx) or {}
        if patch_llm:
            state = merge_state(state, {"ficha": patch_llm.get("ficha", patch_llm)})

    # 3) Confirmación (combinado para el mensaje)
    combined = {"ficha": {}}
    if patch_local:
        combined["ficha"].update(patch_local.get("ficha", patch_local))
    if patch_llm:
        combined["ficha"].update(patch_llm.get("ficha", patch_llm))

    had_any = bool(combined["ficha"])
    confirm = summarize_patch_for_confirmation(combined, module_idx) if had_any else "No pude extraer datos de este bloque."

    # 4) LÓGICA DE AVANCE
    #    => Si estamos en módulo 0 y el patch es SOLO "_start", NO avanzar.
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
        # Si no hubo datos (o era solo _start), marcamos fallo solo si realmente no hubo nada útil
        state._last_failed_module = None if start_only else module_idx

    # 5) Siguiente prompt
    next_idx, next_prompt = advance_module(state)
    if next_idx is None:
        reply = f"{confirm} ¡Listo! Completamos todos los bloques."
    else:
        # nos aseguramos de preguntar el prompt del módulo actual
        state.module_idx = next_idx
        reply = f"{confirm} {next_prompt}"
    return reply, state

# ====== HTTP ======
@router.post("/webhook")
async def webhook(req: Request):
    payload = await req.json()

    text, message_id = _extract_incoming(payload)

    # Ignorar eventos sin texto o de estado / tipos no soportados
    if text == "__IGNORE__":
        return JSONResponse({"ok": True, "ignored": "non_text_or_status"})

    # Siempre usar el hardcode
    user_id = HARDCODED_USER_ID
    state = load_state(user_id)

    # --- Desduplicación por message_id ---
    if message_id and message_id in state._handled_msg_ids:
        return JSONResponse({"ok": True, "ignored": "duplicate_message"})
    if message_id:
        state._handled_msg_ids.add(message_id)

    # --- Anti-spam “No pude…” ---
    if text == state._last_text and state._last_failed_module == state.module_idx:
        return JSONResponse({"ok": True, "ignored": "same_text_same_module"})

    reply, state = _triage_block(state, text)
    save_state(state)
    state._last_text = text  # actualizar último texto

    # Enviar por WhatsApp (solo si hay reply no vacío)
    sent = False
    if reply:
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
