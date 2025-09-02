# routes.py
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from typing import Dict, Any, Tuple
from datetime import datetime

from core.settings import settings
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

# En lugar de FastAPI, usamos APIRouter para ser incluido desde main.py
router = APIRouter()

# ====== Almacenamiento en memoria (cambiá por Redis/DB en prod) ======
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


def _infer_user_id(payload: Dict[str, Any]) -> str:
    # intenta varias claves comunes de WhatsApp providers
    for k in ["from", "from_number", "wa_id", "sender", "user_id", "phone"]:
        v = payload.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip()
        if isinstance(v, dict) and "id" in v and v["id"]:
            return str(v["id"])
    # fallback: una sesión única por IP (no ideal)
    return "anon"


# ====== Core TRIAGE ======
def _triage_block(state: ConversationState, text: str) -> Tuple[str, ConversationState]:
    """Procesa el texto en el módulo actual, con parsers locales y fallback LLM según aplique."""
    module_idx = state.module_idx
    patch_local = fill_from_text_modular(state, module_idx, text or "")
    if patch_local:
        state = merge_state(state, {"ficha": patch_local.get("ficha", patch_local)})

    # si faltan obligatorios y el módulo usa LLM → fallback
    missing = True
    if MODULES[module_idx]["required"]:
        missing = len([m for m in MODULES[module_idx]["required"] if m]) > 0 and False  # no nos sirve así
        # Recalcular missing de verdad sobre el estado ya mergeado:

    # Simple recheck: si el módulo usa LLM y el estado no tiene el nodo completo:
    needs_llm = MODULES[module_idx]["use_llm"]
    did_llm = False
    if needs_llm:
        # estrategia: si el local no cubrió el bloque (o siempre para 5–7 si hay texto), llamamos LLM
        patch_llm = llm_parse_modular(text or "", module_idx)
        if patch_llm:
            did_llm = True
            state = merge_state(state, {"ficha": patch_llm.get("ficha", patch_llm)})

    # confirmación por bloque + próxima pregunta
    confirm = summarize_patch_for_confirmation({"ficha": patch_local.get("ficha", {})} if patch_local else {"ficha": {}}, module_idx)
    # avanzamos si el bloque tiene lo necesario (o no requiere nada)
    # Avance mínimo: pasamos al siguiente módulo
    state.module_idx = min(state.module_idx + 1, len(MODULES) - 1)
    next_idx, next_prompt = advance_module(state)
    if next_idx is None:
        reply = f"{confirm}. ¡Listo! Completamos todos los bloques."
    else:
        # ponemos el puntero en el siguiente índice detectado por advance
        state.module_idx = next_idx
        reply = f"{confirm}. ¿Falta algo de este bloque? Si no, sigamos. {next_prompt}"
    return reply, state


# ====== HTTP ======
@router.post("/webhook")
async def webhook(req: Request):
    payload = await req.json()
    text = payload.get("text") or payload.get("message") or ""

    #user_id = "542616463629"
    user_id = _infer_user_id(payload)

    state = load_state(user_id)
    reply, state = _triage_block(state, text)
    save_state(state)

    return JSONResponse({"to": user_id, "reply": reply, "module": MODULES[state.module_idx]["name"]})


@router.get("/health")
def health():
    return {"ok": True}
