# core/steps.py
from __future__ import annotations

from typing import Any, Dict, Optional, Tuple
import re


# ============================================================================
# Definición de módulos
# - name: nombre legible del bloque
# - use_llm: si ese bloque debería intentar parseo "inteligente" (aquí: False)
# - prompt: texto guía para el siguiente input del usuario
# Podés ajustar prompts, orden y cantidad sin romper las firmas públicas.
# ============================================================================
MODULES = [
    {
        "name": "Identificación",
        "use_llm": False,
        "prompt": "¿Cuál es tu nombre y apellido? Podés escribir: 'Me llamo Ana Pérez'.",
    },
    {
        "name": "Datos demográficos",
        "use_llm": False,
        "prompt": "¿Cuál es tu edad (en años) y sexo (M/F)? Ej: 'Tengo 34 años, F'.",
    },
    {
        "name": "Signos/antropometría",
        "use_llm": False,
        "prompt": "Si querés, agregá peso (kg) y talla (cm). Ej: 'Peso 70 kg y mido 165 cm'.",
    },
]


# ============================================================================
# Helpers de parseo muy livianos (reglas) para evitar dependencia circular
# y mantener un comportamiento estable si no hay parsers “LLM”.
# ============================================================================

def _ensure_ficha(state: Any) -> None:
    """Garantiza que el objeto state tenga el dict 'ficha'."""
    if not hasattr(state, "ficha") or state.ficha is None:
        setattr(state, "ficha", {})


def merge_state(state: Any, patch: Dict[str, Any]) -> Any:
    """
    Fusiona un patch en el estado.
    Acepta tanto {"ficha": {...}} como {...} directo.
    Devuelve el propio state para encadenar.
    """
    _ensure_ficha(state)

    data = patch.get("ficha", patch)
    if not isinstance(data, dict):
        return state

    # Merge superficial (no deep-merge recursivo)
    for k, v in data.items():
        state.ficha[k] = v
    return state


def prompt_for_module(idx: int) -> str:
    """Devuelve el prompt guía del módulo idx (con fallback seguro)."""
    if 0 <= idx < len(MODULES):
        return MODULES[idx].get("prompt") or f"Completá el bloque: {MODULES[idx]['name']}."
    return "Continuemos con el siguiente bloque."


def advance_module(state: Any) -> Tuple[Optional[int], Optional[str]]:
    """
    Indica el 'siguiente' módulo a pedir, dada la posición actual en state.module_idx.
    Convención usada por routes.py:
      - Si ya estamos en el último módulo, devolver (None, None) para marcar fin.
      - En caso contrario, devolver (idx_actual, prompt_de_ese_módulo).
    OJO: routes.py incrementa module_idx cuando hubo datos; aquí no lo tocamos.
    """
    idx = getattr(state, "module_idx", 0) or 0
    # Normalizamos idx por si viene fuera de rango
    if idx < 0:
        idx = 0
    if idx >= len(MODULES) - 1:
        # Si está en el último (o más allá), no hay siguiente
        return None, None
    # Si no estamos en el último, el “siguiente a preguntar” es el índice actual
    return idx, prompt_for_module(idx)


# ============================================================================
# Parsers modulares (reglas simples). Si no matchean, devuelven {}.
# Esto permite que el flujo siga funcionando aunque el usuario envíe texto libre.
# ============================================================================

_name_re = re.compile(r"(?:me\s+llamo|soy|nombre\s*:\s*)(?P<nombre>[\wÀ-ÿ'\- ]{3,})", re.IGNORECASE)
_age_re = re.compile(r"(?P<edad>\d{1,3})\s*(?:años|año)?", re.IGNORECASE)
_sex_re = re.compile(r"\b(?P<sexo>[MFmf])\b")
_weight_re = re.compile(r"(?:peso|pesa|kg)\D{0,5}(?P<peso>\d{1,3})(?:[.,]\d)?", re.IGNORECASE)
_height_re = re.compile(r"(?:mido|talla|cm)\D{0,5}(?P<talla>\d{2,3})(?:[.,]\d)?", re.IGNORECASE)


def _parse_identificacion(text: str) -> Dict[str, Any]:
    patch: Dict[str, Any] = {}
    m = _name_re.search(text or "")
    if m:
        patch["nombre_completo"] = m.group("nombre").strip()
    return patch


def _parse_demografia(text: str) -> Dict[str, Any]:
    patch: Dict[str, Any] = {}
    m_age = _age_re.search(text or "")
    if m_age:
        try:
            age = int(m_age.group("edad"))
            if 0 < age < 130:
                patch["edad"] = age
        except Exception:
            pass
    m_sex = _sex_re.search(text or "")
    if m_sex:
        patch["sexo"] = m_sex.group("sexo").upper()
    return patch


def _parse_antropometria(text: str) -> Dict[str, Any]:
    patch: Dict[str, Any] = {}
    m_w = _weight_re.search(text or "")
    if m_w:
        try:
            patch["peso_kg"] = int(m_w.group("peso"))
        except Exception:
            pass
    m_h = _height_re.search(text or "")
    if m_h:
        try:
            patch["talla_cm"] = int(m_h.group("talla"))
        except Exception:
            pass
    return patch


_PARSERS = {
    0: _parse_identificacion,
    1: _parse_demografia,
    2: _parse_antropometria,
}


def fill_from_text_modular(state: Any, module_idx: int, text: str) -> Dict[str, Any]:
    """
    Parser “local” por módulo (reglas simples).
    Devuelve {"ficha": {...}} si encuentra algo; si no, {}.
    """
    parser = _PARSERS.get(module_idx)
    if not parser:
        return {}
    data = parser(text or "")
    return {"ficha": data} if data else {}


def llm_parse_modular(text: str, module_idx: int) -> Dict[str, Any]:
    """
    Placeholder para un parser “LLM”. Como en MODULES.use_llm lo tenemos en False,
    normalmente no se invoca. Igual devolvemos {} para mantener la firma.
    """
    return {}


def summarize_patch_for_confirmation(patch: Dict[str, Any], module_idx: int) -> str:
    """
    Crea un texto corto confirmando lo que se capturó en el bloque actual.
    Acepta formas con o sin 'ficha'. Si no hay datos, devuelve un mensaje neutro.
    """
    ficha = patch.get("ficha", patch) or {}
    if not isinstance(ficha, dict) or not ficha:
        return "No pude extraer datos de este bloque."

    # Armamos una lista "clave: valor" ordenada para confirmación breve
    items = []
    for k, v in ficha.items():
        items.append(f"{k}: {v}")

    modulo_name = MODULES[module_idx]["name"] if 0 <= module_idx < len(MODULES) else "Bloque"
    joined = "; ".join(items)
    return f"Anoté en {modulo_name}: {joined}."
