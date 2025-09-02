# steps.py
from typing import Dict, Any, List

# Orden y textos de las preguntas
QUESTION_FLOW = [
    "alergias",
    "talla_cm",
    "peso_kg",
    "ayuno_horas",
    "asa",
]

QUESTION_TEXT: Dict[str, str] = {
    "alergias": "¿Tenés alguna alergia a medicamentos o alimentos?",
    "talla_cm": "¿Cuál es tu estatura en centímetros?",
    "peso_kg": "¿Cuál es tu peso en kilogramos?",
    "ayuno_horas": "¿Cuántas horas de ayuno llevás?",
    "asa": "¿Sabés tu clasificación ASA (I, II, III o IV)? Si no, lo vemos luego.",
}

REPROMPT_HINT: Dict[str, str] = {
    "alergias": "Respondé con 'sí' o 'no'. Si tenés, podés decir: “alérgico a penicilina”.",
    "talla_cm": "Ejemplo: 172",
    "peso_kg": "Ejemplo: 68.5",
    "ayuno_horas": "Ejemplo: 8",
    "asa": "Ejemplo: ASA II",
}


def _get_meta(state: Dict[str, Any]) -> Dict[str, Any]:
    if "_meta" not in state:
        state["_meta"] = {"last_field": None, "retries": 0}
    if "last_field" not in state["_meta"]:
        state["_meta"]["last_field"] = None
    if "retries" not in state["_meta"]:
        state["_meta"]["retries"] = 0
    return state["_meta"]


def next_field(current: str | None) -> str | None:
    if current is None:
        return QUESTION_FLOW[0]
    try:
        i = QUESTION_FLOW.index(current)
        return QUESTION_FLOW[i + 1] if i + 1 < len(QUESTION_FLOW) else None
    except ValueError:
        return QUESTION_FLOW[0]


def field_was_filled(field: str, prev: Dict[str, Any], new: Dict[str, Any]) -> bool:
    if field == "alergias":
        p = (prev.get("alergias") or {}).get("tiene_alergias")
        n = (new.get("alergias") or {}).get("tiene_alergias")
        return (n is not None) and (n != p)
    if field == "talla_cm":
        return (new.get("antropometria") or {}).get("talla_cm") != (prev.get("antropometria") or {}).get("talla_cm")
    if field == "peso_kg":
        return (new.get("antropometria") or {}).get("peso_kg") != (prev.get("antropometria") or {}).get("peso_kg")
    if field == "ayuno_horas":
        return new.get("ayuno_horas") != prev.get("ayuno_horas")
    if field == "asa":
        n = (new.get("evaluacion_preoperatoria") or {}).get("asa") or new.get("asa")
        p = (prev.get("evaluacion_preoperatoria") or {}).get("asa")
        return (n is not None) and (n != p)
    return False


def build_confirms(prev: Dict[str, Any], new: Dict[str, Any]) -> List[str]:
    confirms: List[str] = []
    ant_new = new.get("antropometria") or {}
    ant_prev = prev.get("antropometria") or {}

    if ant_new.get("talla_cm") and ant_new.get("talla_cm") != ant_prev.get("talla_cm"):
        try:
            confirms.append(f"Estatura: {int(ant_new['talla_cm'])} cm")
        except Exception:
            confirms.append(f"Estatura: {ant_new['talla_cm']} cm")

    if ant_new.get("peso_kg") and ant_new.get("peso_kg") != ant_prev.get("peso_kg"):
        confirms.append(f"Peso: {ant_new['peso_kg']} kg")

    if ant_new.get("imc") and ant_new.get("imc") != ant_prev.get("imc"):
        confirms.append(f"IMC: {ant_new['imc']}")

    alerg_new = new.get("alergias") or {}
    alerg_prev = prev.get("alergias") or {}
    if alerg_new.get("tiene_alergias") is True and alerg_new.get("tiene_alergias") != alerg_prev.get("tiene_alergias"):
        confirms.append("Alergias: sí")
    elif alerg_new.get("tiene_alergias") is False and alerg_new.get("tiene_alergias") != alerg_prev.get("tiene_alergias"):
        confirms.append("Alergias: no")

    asa_new = (new.get("evaluacion_preoperatoria") or {}).get("asa") or new.get("asa")
    asa_prev = (prev.get("evaluacion_preoperatoria") or {}).get("asa")
    if asa_new and asa_new != asa_prev:
        confirms.append(f"ASA: {asa_new}")

    return confirms


def init_state_for_dni() -> Dict[str, Any]:
    """Estado inicial cuando entramos a triage tras registrar el DNI."""
    return {"_meta": {"last_field": "alergias", "retries": 0}}


def compute_reply(prev_state: Dict[str, Any], updated_state: Dict[str, Any]) -> str:
    """
    Decide si avanzamos, repreguntamos y arma el mensaje final a enviar.
    Mutará _meta dentro de updated_state para mantener el puntero y reintentos.
    """
    meta = _get_meta(updated_state)
    expected = meta.get("last_field") or next_field(None)

    filled = field_was_filled(expected, prev_state, updated_state)
    confirms = build_confirms(prev_state, updated_state)
    confirm_txt = ("Anoté: " + "; ".join(confirms) + ". ") if confirms else ""

    if filled:
        meta["retries"] = 0
        nxt = next_field(expected)
        meta["last_field"] = nxt
        if nxt is None:
            return confirm_txt + "¡Listo! No tengo más preguntas por ahora. ✅"
        return confirm_txt + QUESTION_TEXT[nxt]

    # Repregunta del mismo campo
    meta["last_field"] = expected
    meta["retries"] = meta.get("retries", 0) + 1
    hint = REPROMPT_HINT.get(expected, "")
    if meta["retries"] == 1:
        return f"No me quedó claro. {QUESTION_TEXT[expected]} {hint}"
    return f"Perdón, sigo sin entender. {QUESTION_TEXT[expected]} {hint}"
