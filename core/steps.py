# core/steps.py
from __future__ import annotations

from typing import Any, Dict, Optional, Tuple
import re

# ============================================================================
# Definición de MÓDULOS (en orden)
# ============================================================================
MODULES = [
    {
        "name": "DNI",
        "use_llm": False,
        "prompt": "Para empezar, decime tu DNI (solo números, sin puntos ni espacios). Ej: 12345678",
    },
    {
        "name": "Datos personales",
        "use_llm": False,
        "prompt": "Nombre y apellido, y tu fecha de nacimiento (dd/mm/aaaa). También podés indicar sexo (M/F).",
    },
    {
        "name": "Antropometría",
        "use_llm": False,
        "prompt": "Decime peso (kg) y talla (cm o en metros). Ej: 'Peso 70 kg y mido 1.65 m'.",
    },
    {
        "name": "Cobertura y motivo",
        "use_llm": False,
        "prompt": "¿Cuál es tu obra social (o prepaga) y nro. de afiliado? ¿Motivo de la cirugía?",
    },
    {
        "name": "Alergias y medicación",
        "use_llm": False,
        "prompt": "¿Tenés alergias? ¿Tomás medicación habitual? Indicá nombres/dosis si podés.",
    },
    {
        "name": "Antecedentes",
        "use_llm": False,
        "prompt": "Contame antecedentes relevantes (cardíacos, respiratorios, HTA, DM, cirugías previas, etc.).",
    },
    {
        "name": "Estudios complementarios",
        "use_llm": False,
        "prompt": "¿Tenés estudios/laboratorio recientes? Podés escribir el resumen y la fecha.",
    },
    {
        "name": "Sustancias",
        "use_llm": False,
        "prompt": "Consumo de tabaco, alcohol u otras sustancias. Indicá cantidad/frecuencia si aplica.",
    },
    {
        "name": "Vía aérea",
        "use_llm": False,
        "prompt": "Datos de vía aérea si los tenés (Mallampati, apertura bucal, piezas dentarias, prótesis).",
    },
]

# ============================================================================
# Helpers
# ============================================================================

def _ensure_ficha(state: Any) -> None:
    """
    Garantiza que state.ficha exista. Si es None, instancia FichaPreanestesia().
    Import tardío para evitar ciclos.
    """
    if not hasattr(state, "ficha") or state.ficha is None:
        try:
            from models.schemas import FichaPreanestesia  # type: ignore
            state.ficha = FichaPreanestesia()
        except Exception:
            state.ficha = {}  # fallback seguro


def merge_state(state: Any, patch: Dict[str, Any]) -> Any:
    """
    Fusiona un patch en el estado.
    Acepta tanto {"ficha": {...}} como {...} directo.
    - Si state.ficha es dict -> asignación por clave
    - Si state.ficha es modelo/objeto -> setattr si el atributo existe
    Ignora claves internas (empiezan con "_").
    """
    _ensure_ficha(state)

    data = patch.get("ficha", patch)
    if not isinstance(data, dict):
        return state

    # Caso dict
    if isinstance(state.ficha, dict):
        for k, v in data.items():
            if isinstance(k, str) and k.startswith("_"):
                continue
            state.ficha[k] = v
        return state

    # Caso objeto (pydantic/dataclass/etc.)
    for k, v in data.items():
        if isinstance(k, str) and k.startswith("_"):
            continue
        if hasattr(state.ficha, k):
            setattr(state.ficha, k, v)
        else:
            # Campo inexistente en el modelo: lo ignoramos
            pass
    return state


def prompt_for_module(idx: int) -> str:
    if 0 <= idx < len(MODULES):
        return MODULES[idx]["prompt"]
    return "Continuemos con el siguiente bloque."


def advance_module(state: Any) -> Tuple[Optional[int], Optional[str]]:
    """
    Devuelve el índice del módulo a preguntar ahora y su prompt.
    Si no quedan módulos, (None, None).
    """
    idx = getattr(state, "module_idx", 0) or 0
    if idx < 0:
        idx = 0
    if idx >= len(MODULES):
        return None, None
    return idx, prompt_for_module(idx)

# ============================================================================
# Regex y parsers específicos por módulo
# ============================================================================

# Saludo/inicio
_GREETING_RE = re.compile(
    r"^\s*(hola|buenas|hey|hi|qué\s*tal|buen\s*d[ií]a|buenas\s*tardes|buenas\s*noches)\b",
    re.IGNORECASE,
)

# DNI
_DNI_RE = re.compile(r"\b(?P<dni>\d{6,10})\b")

# Datos personales
_NAME_RE = re.compile(r"(?:me\s+llamo|soy|nombre\s*:?\s*)(?P<nombre>[\wÀ-ÿ'´`\- ]{3,})", re.IGNORECASE)
_DOB_RE = re.compile(r"\b(?P<d>\d{1,2})[/-](?P<m>\d{1,2})[/-](?P<y>\d{2,4})\b")
_SEX_RE = re.compile(r"\b(?P<sexo>[MFmf])\b")

# Antropometría
_WEIGHT_RE = re.compile(r"(?:peso|pesa|kg)\D{0,5}(?P<peso>\d{1,3})(?:[.,]\d+)?", re.IGNORECASE)
_HEIGHT_RE = re.compile(r"(?:mido|talla|altura|cm|mts?|metros?)\D{0,5}(?P<talla>\d{2,3})(?:[.,]\d+)?", re.IGNORECASE)
_HEIGHT_M_RE = re.compile(r"\b(?P<metros>1(?:[.,]\d{1,2})|0[.,]\d{1,2})\s*m", re.IGNORECASE)

# Cobertura
_OS_RE = re.compile(r"(?:obra\s+social|prepaga|cobertura)\s*:?\s*[- ]*(?P<os>[A-Za-zÀ-ÿ0-9\. '\-]{2,})", re.IGNORECASE)
_AFIL_RE = re.compile(r"(?:nro?\.?\s*afiliad[oa]|afiliad[oa])\s*:?\s*[- ]*(?P<afil>[A-Za-z0-9\-\.]{4,})", re.IGNORECASE)
_MOTIVO_RE = re.compile(r"(?:motivo|cirug[ií]a|procedimiento)\s*:?\s*[- ]*(?P<motivo>[\wÀ-ÿ0-9,\. '\-]{3,})", re.IGNORECASE)

# Alergias/medicación
_ALERG_RE = re.compile(r"(?:alergias?|al[ée]rgico[as]?)\s*:?\s*[- ]*(?P<alergias>.+)", re.IGNORECASE)
_MEDIC_RE = re.compile(r"(?:medicaci[oó]n|tomo|tomas|toma)\s*:?\s*[- ]*(?P<medicacion>.+)", re.IGNORECASE)

# Antecedentes
_ANTEC_RE = re.compile(r"(?:antecedentes?|enfermedades?|patolog[ií]a?s?)\s*:?\s*[- ]*(?P<antecedentes>.+)", re.IGNORECASE)

# Complementarios
_COMPL_RE = re.compile(r"(?:estudios?|laboratorio|lab[s]?|electro|ecg|rx|placa|tc|mri|rmn)\s*:?\s*[- ]*(?P<complementarios>.+)", re.IGNORECASE)

# Sustancias
_TABA_RE = re.compile(r"(?:tabaco|fumo|fum[oé]s?|cigarrillos?)\s*:?\s*[- ]*(?P<tabaco>.+)", re.IGNORECASE)
_ALCO_RE = re.compile(r"(?:alcohol|beb[eo]s?)\s*:?\s*[- ]*(?P<alcohol>.+)", re.IGNORECASE)
_OTRAS_RE = re.compile(r"(?:drogas?|sustancias?)\s*:?\s*[- ]*(?P<otras>.+)", re.IGNORECASE)

# Vía aérea
_VA_RE = re.compile(r"(?:v[ií]a\s*a[ée]rea|mallampati|apertura|bucal|dentari[ao]s?|piezas|pr[oó]tesis)\s*:?\s*[- ]*(?P<via_aerea>.+)", re.IGNORECASE)

def _norm_year(y: int) -> int:
    if y < 100:
        return 2000 + y if y <= 21 else 1900 + y
    return y

# ---------------- DNI ----------------
def _parse_dni(text: str) -> Dict[str, Any]:
    # Saludo inicial: avanza sin error
    if _GREETING_RE.search(text.strip()):
        return {"_start": True}
    m = _DNI_RE.search(text)
    if m:
        return {"dni": m.group("dni")}
    return {}

# ---------------- DATOS PERSONALES ----------------
def _parse_datos(text: str) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    mname = _NAME_RE.search(text)
    if mname:
        out["nombre_completo"] = " ".join(mname.group("nombre").split())
    mdob = _DOB_RE.search(text)
    if mdob:
        d = int(mdob.group("d")); m = int(mdob.group("m")); y = _norm_year(int(mdob.group("y")))
        if 1 <= d <= 31 and 1 <= m <= 12 and 1900 <= y <= 2100:
            out["fecha_nacimiento"] = f"{d:02d}/{m:02d}/{y:04d}"
    msex = _SEX_RE.search(text)
    if msex:
        out["sexo"] = msex.group("sexo").upper()
    return out

# ---------------- ANTROPOMETRÍA ----------------
def _parse_antropometria(text: str) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    mw = _WEIGHT_RE.search(text)
    if mw:
        try:
            out["peso_kg"] = int(mw.group("peso"))
        except Exception:
            pass
    mh = _HEIGHT_RE.search(text)
    if mh:
        try:
            out["talla_cm"] = int(mh.group("talla"))
        except Exception:
            pass
    mm = _HEIGHT_M_RE.search(text)
    if mm and "talla_cm" not in out:
        try:
            metros = float(mm.group("metros").replace(",", "."))
            out["talla_cm"] = int(round(metros * 100))
        except Exception:
            pass
    return out

# ---------------- COBERTURA ----------------
def _parse_cobertura(text: str) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    mo = _OS_RE.search(text)
    if mo:
        val = mo.group("os").strip(" -:")
        if val:
            out["obra_social"] = val
    maf = _AFIL_RE.search(text)
    if maf:
        out["nro_afiliado"] = maf.group("afil").strip()
    mm = _MOTIVO_RE.search(text)
    if mm:
        out["motivo_cirugia"] = mm.group("motivo").strip()
    return out

# ---------------- ALERGIAS / MEDICACIÓN ----------------
def _parse_alerg_med(text: str) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    ma = _ALERG_RE.search(text)
    if ma:
        out["alergias"] = ma.group("alergias").strip()
    mm = _MEDIC_RE.search(text)
    if mm:
        out["medicacion"] = mm.group("medicacion").strip()
    return out

# ---------------- ANTECEDENTES ----------------
def _parse_antecedentes(text: str) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    m = _ANTEC_RE.search(text)
    if m:
        out["antecedentes"] = m.group("antecedentes").strip()
    return out

# ---------------- COMPLEMENTARIOS ----------------
def _parse_complementarios(text: str) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    m = _COMPL_RE.search(text)
    if m:
        out["complementarios"] = m.group("complementarios").strip()
    return out

# ---------------- SUSTANCIAS ----------------
def _parse_sustancias(text: str) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    mt = _TABA_RE.search(text)
    if mt:
        out["tabaco"] = mt.group("tabaco").strip()
    ma = _ALCO_RE.search(text)
    if ma:
        out["alcohol"] = ma.group("alcohol").strip()
    mo = _OTRAS_RE.search(text)
    if mo:
        out["otras_sustancias"] = mo.group("otras").strip()
    return out

# ---------------- VÍA AÉREA ----------------
def _parse_via_aerea(text: str) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    m = _VA_RE.search(text)
    if m:
        out["via_aerea"] = m.group("via_aerea").strip()
    return out

# Mapa índice -> parser
_PARSERS = {
    0: _parse_dni,
    1: _parse_datos,
    2: _parse_antropometria,
    3: _parse_cobertura,
    4: _parse_alerg_med,
    5: _parse_antecedentes,
    6: _parse_complementarios,
    7: _parse_sustancias,
    8: _parse_via_aerea,
}

def fill_from_text_modular(state: Any, module_idx: int, text: str) -> Dict[str, Any]:
    """
    Parser local por módulo (reglas simples).
    - Si detecta saludo en el módulo 0, devuelve {"_start": True} para saludar y avanzar.
    - En general devuelve {"ficha": {...}} o {}.
    """
    parser = _PARSERS.get(module_idx)
    if not parser:
        return {}
    data = parser(text or "")
    if not data:
        return {}
    return {"ficha": data}

def llm_parse_modular(text: str, module_idx: int) -> Dict[str, Any]:
    """Placeholder para parsers basados en LLM si activás use_llm=True en algún módulo."""
    return {}

def summarize_patch_for_confirmation(patch: Dict[str, Any], module_idx: int) -> str:
    """
    Resume lo capturado para confirmación. Evita mostrar flags internos.
    Si detecta solo _start en el módulo 0, devuelve un saludo inicial.
    """
    ficha = patch.get("ficha", patch) or {}
    if not isinstance(ficha, dict):
        return "No pude extraer datos de este bloque."

    if module_idx == 0 and "_start" in ficha and len(ficha) == 1:
        return "¡Hola! Empecemos."

    public_items = [(k, v) for k, v in ficha.items() if not str(k).startswith("_")]
    if not public_items:
        return "No pude extraer datos de este bloque."

    modulo_name = MODULES[module_idx]["name"] if 0 <= module_idx < len(MODULES) else "Bloque"
    joined = "; ".join(f"{k}: {v}" for k, v in public_items)
    return f"Anoté en {modulo_name}: {joined}."
