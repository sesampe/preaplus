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
)

router = APIRouter()
wa_client = WhatsApp(token=HEYOO_TOKEN, phone_number_id=HEYOO_PHONE_ID)

# Hardcodeá tu número de prueba acá
HARDCODED_USER_ID = "542616463629"

# ====== Memoria simple en-proc ======
_USER_STATE: Dict[str, ConversationState] = {}

def load_state(user_id: str) -> ConversationState:
    st = _USER_STATE.get(user_id)
    if st is None:
        st = ConversationState(user_id=user_id)
        st._handled_msg_ids = set()
        st._last_text = ""
        st._last_failed_module = None
        st._has_greeted = False
        st.module_idx = 0
        _USER_STATE[user_id] = st
    # compat
    if not hasattr(st, "_handled_msg_ids"):
        st._handled_msg_ids = set()
    if not hasattr(st, "_last_text"):
        st._last_text = ""
    if not hasattr(st, "_last_failed_module"):
        st._last_failed_module = None
    if not hasattr(st, "_has_greeted"):
        st._has_greeted = False
    if not hasattr(st, "module_idx") or st.module_idx is None:
        st.module_idx = 0
    return st

def save_state(state: ConversationState):
    state.updated_at = datetime.utcnow()
    _USER_STATE[state.user_id] = state

# ====== Helpers ======
def _extract_incoming(payload: Dict[str, Any]) -> Tuple[str, Optional[str]]:
    """Devuelve (text, message_id) o ('__IGNORE__', None) si es status/otro tipo."""
    try:
        entry = payload.get("entry", [])[0]
        change = entry.get("changes", [])[0]
        value = change.get("value", {})

        if value.get("statuses"):  # callbacks de delivery/read
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

    # modo test local
    text = payload.get("text") or payload.get("message") or payload.get("body") or ""
    mid = payload.get("message_id")
    if not text:
        return "__IGNORE__", mid
    return text, mid

def _dig(obj: Any, path: list[str]) -> Any:
    cur = obj
    for k in path:
        if cur is None:
            return None
        if isinstance(cur, dict):
            cur = cur.get(k)
        else:
            cur = getattr(cur, k, None)
    return cur

def _to_dict(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {k: _to_dict(v) for k, v in obj.items()}
    if hasattr(obj, "model_dump"):  # pydantic v2
        return obj.model_dump()
    if hasattr(obj, "dict"):  # pydantic v1
        return obj.dict()
    if hasattr(obj, "__dict__"):
        return {k: _to_dict(v) for k, v in vars(obj).items()}
    if isinstance(obj, (list, tuple)):
        return [_to_dict(x) for x in obj]
    return obj

def _has(v):
    return v not in (None, "", [], {})

def _missing_mod0_required(state) -> list[str]:
    """Valida obligatorios del módulo 0 en el estado actual."""
    missing = []
    if not _has(_dig(state, ["ficha", "dni"])): missing.append("DNI (solo números)")
    if not _has(_dig(state, ["ficha", "datos", "nombre_completo"])): missing.append("Nombre y apellido")
    if not _has(_dig(state, ["ficha", "datos", "fecha_nacimiento"])): missing.append("Fecha nacimiento (dd/mm/aaaa)")
    if not _has(_dig(state, ["ficha", "antropometria", "peso_kg"])): missing.append("Peso kg")
    if not _has(_dig(state, ["ficha", "antropometria", "talla_cm"])): missing.append("Talla cm")
    if not _has(_dig(state, ["ficha", "cobertura", "obra_social"])): missing.append("Obra social")
    if not _has(_dig(state, ["ficha", "cobertura", "afiliado"])): missing.append("N° afiliado")
    if not _has(_dig(state, ["ficha", "cobertura", "motivo_cirugia"])): missing.append("Motivo de consulta")
    return missing

def _missing_form_snippet(missing: list[str]) -> str:
    """Snippet de solo los campos faltantes en negrita (WhatsApp: *texto*)."""
    mapping = {
        "Nombre y apellido": "*Nombre y apellido:*",
        "DNI (solo números)": "*DNI (solo números):*",
        "Fecha nacimiento (dd/mm/aaaa)": "*Fecha nacimiento (dd/mm/aaaa):*",
        "Peso kg": "*Peso kg (ej 72.5):*",
        "Talla cm": "*Talla cm (ej 170):*",
        "Obra social": "*Obra social:*",
        "N° afiliado": "*N° afiliado:*",
        "Motivo de consulta": "*Motivo de consulta (breve):*",
    }
    lines = [mapping[m] for m in missing if m in mapping]
    return "\n".join(lines)

# ====== Core TRIAGE ======
def _triage_block(state: ConversationState, text: str) -> Tuple[list[str], ConversationState]:
    module_idx = state.module_idx

    # 1) Patch local (regex/fallbacks)
    patch_local = fill_from_text_modular(state, module_idx, text or "")
    if patch_local:
        state = merge_state(state, {"ficha": patch_local.get("ficha", patch_local)})

    # 2) Patch LLM (si el módulo lo usa) — EXTRAEMOS datos libres del módulo 0,
    #    además de normalizar el motivo.
    patch_llm: Dict[str, Any] = {}
    if 0 <= module_idx < len(MODULES) and MODULES[module_idx].get("use_llm"):
        patch_llm = llm_parse_modular(text or "", module_idx) or {}
        if patch_llm:
            state = merge_state(state, {"ficha": patch_llm.get("ficha", patch_llm)})

    # 3) Confirmación basada en TODO el estado acumulado
    snapshot = {"ficha": _to_dict(getattr(state, "ficha", {}))}
    confirm = summarize_patch_for_confirmation(snapshot, module_idx)

    # 4) Lógica de avance y faltantes (solo módulo 0)
    messages: list[str] = []
    if module_idx == 0:
        faltan = _missing_mod0_required(state)
        if faltan:
            # no avanzar; explicar y pedir solo lo faltante
            if confirm:  # solo si hay algo para mostrar
                messages.append(confirm)
            messages.append("Me faltó completar estos campos. Copiá y pegá este mini-formulario y rellenalo:")
            messages.append(_missing_form_snippet(faltan))
            state._last_failed_module = module_idx
            return messages, state

    # Si no faltan, avanzamos
    state.module_idx = min(state.module_idx + 1, len(MODULES) - 1)
    state._last_failed_module = None

    # 5) Siguiente prompt
    next_idx, next_prompt = advance_module(state)
    if next_idx is None:
        if confirm:
            messages.append(f"{confirm} ¡Listo! Completamos todos los bloques.")
        else:
            messages.append("¡Listo! Completamos todos los bloques.")
    else:
        if confirm:
            messages.append(confirm)
        messages.append(next_prompt)

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

    # Desduplicación básica
    if message_id and message_id in state._handled_msg_ids:
        return JSONResponse({"ok": True, "ignored": "duplicate_message"})
    if message_id:
        state._handled_msg_ids.add(message_id)

    # Primer contacto: SIEMPRE saludar. Si no trae datos, enviar formulario.
    if not state._has_greeted:
        saludo = (
            "Hola, vamos a completar tu ficha anestesiologica."
        )
        wa_client.send_message(message=saludo, recipient_id=user_id)

        state._has_greeted = True
        save_state(state)

        preview = fill_from_text_modular(state, state.module_idx, text or "") or {}
        has_data = bool(preview and (preview.get("ficha") or preview))
        if not has_data:
            wa_client.send_message(
                message="COPIA, PEGA Y RELLENA CON TUS DATOS EL SIGUIENTE FORMULARIO",
                recipient_id=user_id,
            )
            wa_client.send_message(message=MODULES[0]['prompt'], recipient_id=user_id)
            return JSONResponse({
                "to": user_id,
                "echo_text": text,
                "replies": [saludo, "COPIA, PEGA Y RELLENA CON TUS DATOS EL SIGUIENTE FORMULARIO", MODULES[0]["prompt"]],
                "sent": [True, True, True],
                "module": MODULES[state.module_idx]["name"],
            })
        # Si trae datos, seguimos al triage normal con ese mismo texto.

    # Anti-bucle
    if text == state._last_text and state._last_failed_module == state.module_idx:
        return JSONResponse({"ok": True, "ignored": "same_text_same_module"})

    # Triage normal
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
