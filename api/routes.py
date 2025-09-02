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

# ====== Core TRIAGE ======
def _triage_block(state: ConversationState, text: str) -> Tuple[str, ConversationState]:
    module_idx = state.module_idx
    patch_local = fill_from_text_modular(state, module_idx, text or "")
    if patch_local:
        state = merge_state(state, {"ficha": patch_local.get("ficha", patch_local)})

    needs_llm = MODULES[module_idx]["use_llm"]
    if needs_llm:
        patch_llm = llm_parse_modular(text or "", module_idx)
        if patch_llm:
            state = merge_state(state, {"ficha": patch_llm.get("ficha", patch_llm)})

    confirm = summarize_patch_for_confirmation(
        {"ficha": patch_local.get("ficha", {})} if patch_local else {"ficha": {}}, 
        module_idx
    )

    state.module_idx = min(state.module_idx + 1, len(MODULES) - 1)
    next_idx, next_prompt = advance_module(state)
    if next_idx is None:
        reply = f"{confirm}. ¡Listo! Completamos todos los bloques."
    else:
        state.module_idx = next_idx
        reply = f"{confirm}. ¿Falta algo de este bloque? Si no, sigamos. {next_prompt}"
    return reply, state

# ====== HTTP ======
@router.post("/webhook")
async def webhook(req: Request):
    payload = await req.json()
    # Intentá extraer texto desde distintos formatos
    text = (
        payload.get("text") 
        or payload.get("message") 
        or payload.get("body")
    )
    if not text and "messages" in payload:
        msgs = payload["messages"]
        if isinstance(msgs, list) and msgs and "text" in msgs[0]:
            text = msgs[0]["text"].get("body")

    # Siempre usar el hardcode
    user_id = HARDCODED_USER_ID

    state = load_state(user_id)
    reply, state = _triage_block(state, text or "")
    save_state(state)

    # Enviar por WhatsApp
    try:
        wa_client.send_message(message=reply, recipient_id=user_id)
        sent = True
    except Exception as e:
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
