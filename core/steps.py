from __future__ import annotations

from typing import Any, Dict, Optional, Tuple, get_origin, get_args
from pydantic import BaseModel
import re
import os
import json
from datetime import date

# ============================================================================
# Definición de MÓDULOS
# ============================================================================
MODULES = [
    {
        "name": "Datos generales",
        "use_llm": True,  # usar LLM para extraer libres y normalizar (incluye motivo_cirugia)
        "prompt": (
            "Nombre y apellido:\n"
            "DNI (solo números):\n"
            "Fecha nacimiento (dd/mm/aaaa):\n"
            "Peso kg (ej 72.5):\n"
            "Talla cm (ej 170):\n"
            "Obra social:\n"
            "N° afiliado:\n"
            "Motivo de consulta (breve):"
        ),
    },
    {
        "name": "Alergias",
        "use_llm": True,
        "prompt": (
            "¿Tenés *alguna alergia conocida*? (comidas, medicación, látex, etc.)\n"
            "Si la tenés, contame *a qué* y *qué te pasó* en tus palabras (ej: ronchas/rash, "
            "hinchazón, falta de aire, picazón, shock). Si no, decí: \"no alergias conocidas\"."
        ),
    },
    {
        "name": "Medicación habitual",
        "use_llm": True,
        "prompt": (
            "¿Tomás medicación habitual, *incluyendo puff/inhaladores*? Podés decir el *nombre "
            "comercial* si no sabés el genérico. Si sabés la *dosis en mg* que figura en el blister, "
            "mejor. Si no la sabés, no pasa nada.\n"
            "Ejemplos: \"Enalapril 10 mg cada mañana\", \"Sertal\", \"Seretide puff 2 veces al día\"."
        ),
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
# Helpers de estado y merge
# ============================================================================

def _ensure_ficha(state: Any) -> None:
    if not hasattr(state, "ficha") or state.ficha is None:
        try:
            from models.schemas import FichaPreanestesia  # type: ignore
            state.ficha = FichaPreanestesia()
        except Exception:
            state.ficha = {}

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

def _deep_merge_dict(a: Dict[str, Any], b: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(a or {})
    for k, v in (b or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge_dict(out[k], v)
        else:
            out[k] = v
    return out

def _unwrap_optional(tp):
    origin = get_origin(tp)
    if origin is None:
        return tp
    if origin is getattr(__import__("typing"), "Union", None):
        args = [a for a in get_args(tp) if a is not type(None)]
        return args[0] if args else tp
    return tp

def _coerce_to_field_model(parent_model: BaseModel, key: str, value):
    """Convierte dicts a submodelos si el destino es un campo Pydantic."""
    try:
        fields = getattr(parent_model.__class__, "model_fields", None) or {}
        field = fields.get(key)
        if not field:
            return value
        target = _unwrap_optional(field.annotation)
        if isinstance(value, dict) and isinstance(target, type) and issubclass(target, BaseModel):
            return target.model_validate(value)
    except Exception:
        pass
    return value

def merge_state(state: Any, patch: Dict[str, Any]) -> Any:
    """
    Deep-merge del patch en state.ficha (soporta dict o modelos Pydantic).
    Convierte dicts a submodelos cuando el destino es Pydantic para evitar warnings.
    Ignora claves internas (empiezan con '_').
    """
    _ensure_ficha(state)
    inc = patch.get("ficha", patch)
    if not isinstance(inc, dict):
        return state

    current = _to_dict(state.ficha)
    inc = {k: v for k, v in inc.items() if not (isinstance(k, str) and k.startswith("_"))}
    merged = _deep_merge_dict(current, inc)

    if isinstance(state.ficha, dict):
        state.ficha.clear()
        state.ficha.update(merged)
        return state

    if isinstance(state.ficha, BaseModel):
        for k, v in merged.items():
            v = _coerce_to_field_model(state.ficha, k, v)
            try:
                setattr(state.ficha, k, v)
            except Exception:
                pass
        return state

    for k, v in merged.items():
        try:
            setattr(state.ficha, k, v)
        except Exception:
            pass
    return state

def prompt_for_module(idx: int) -> str:
    if 0 <= idx < len(MODULES):
        return MODULES[idx]["prompt"]
    return "Continuemos con el siguiente bloque."

def advance_module(state: Any) -> Tuple[Optional[int], Optional[str]]:
    idx = getattr(state, "module_idx", 0) or 0
    if idx < 0:
        idx = 0
    if idx >= len(MODULES):
        return None, None
    return idx, prompt_for_module(idx)

# ============================================================================
# Regex y parsers del Módulo 0
# ============================================================================
_RE_FLAGS = re.IGNORECASE | re.MULTILINE

_RE_NOMBRE = re.compile(
    r"^nombre y apellido:\s*([A-Za-zÁÉÍÓÚÜÑñ'´`\- ]{3,}(?:\s+[A-Za-zÁÉÍÓÚÜÑñ'´`\- ]{2,})+)\s*$",
    _RE_FLAGS,
)
_RE_DNI_LABELED = re.compile(r"^dni.*?:\s*([0-9][0-9.\s]{5,})$", _RE_FLAGS)
_RE_FNAC = re.compile(r"^fecha nacimiento.*?:\s*(\d{1,2}/\d{1,2}/\d{4})$", _RE_FLAGS)
_RE_PESO = re.compile(r"^peso.*?kg.*?:\s*([0-9]{1,3}(?:[.,][0-9]{1,2})?)$", _RE_FLAGS)
# Talla: permite 170, 1.70 o 1,70
_RE_TALLA = re.compile(r"^talla.*?:\s*([0-9]{1,3}(?:[.,][0-9]{1,2})?)$", _RE_FLAGS)
_RE_OS = re.compile(r"^obra social:\s*([A-Za-zÁÉÍÓÚÜÑñ0-9 .,'\-]{2,60})$", _RE_FLAGS)
_RE_AFIL = re.compile(r"^(?:n°|nº|num(?:ero)?)[\s_-]*afiliad[oa]:\s*([A-Za-z0-9\-./]{3,30})$", _RE_FLAGS)
_RE_MOTIVO = re.compile(r"^motivo.*?:\s*(.{3,200})$", _RE_FLAGS)

# Fallbacks libres
_GREETING_RE = re.compile(r"^\s*(hola|buenas|hey|hi|qué\s*tal|buen\s*d[ií]a|buenas\s*tardes|buenas\s*noches)\b", re.IGNORECASE)
_DNI_FREE_RE = re.compile(r"\b(?P<dni>\d{6,10})\b")
_NAME_FREE_RE = re.compile(
    r"(?:me\s+llamo|soy|nombre(?:\s+y\s+apellido)?\s*:?\s*)(?P<nombre>[\wÀ-ÿ'´`\- ]{3,})",
    re.IGNORECASE,
)
_DOB_FREE_RE = re.compile(r"\b(?P<d>\d{1,2})[/-](?P<m>\d{1,2})[/-](?P<y>\d{2,4})\b")
_WEIGHT_FREE_RE = re.compile(r"(?:peso|pesa|kg)\D{0,5}(?P<peso>\d{1,3}(?:[.,]\d{1,2})?)", re.IGNORECASE)
_HEIGHT_FREE_CM_RE = re.compile(r"(?:mido|talla|altura|cm|mts?|metros?)\D{0,5}(?P<talla>\d{2,3})(?:[.,]\d+)?", re.IGNORECASE)
_HEIGHT_FREE_M_RE = re.compile(r"\b(?P<metros>1(?:[.,]\d{1,2})|0[.,]\d{1,2})\s*m\b", re.IGNORECASE)
_OS_FREE_RE = re.compile(r"(?:obra\s+social|prepaga|cobertura)\s*:?\s*[- ]*(?P<os>[A-Za-zÀ-ÿ0-9\. '\-]{2,})", re.IGNORECASE)
_AFIL_FREE_RE = re.compile(r"(?:nro?\.?\s*afiliad[oa]|afiliad[oa])\s*:?\s*[- ]*(?P<afil>[A-Za-z0-9\-\.\/]{3,})", re.IGNORECASE)
_MOTIVO_FREE_RE = re.compile(r"(?:motivo|cirug[ií]a|procedimiento)\s*:?\s*[- ]*(?P<motivo>[\wÀ-ÿ0-9,\. '\-]{3,})", re.IGNORECASE)

# Limpia markup de WhatsApp
def _strip_whatsapp_markup(s: str) -> str:
    """Quita * de negrita/cursiva y caracteres invisibles LRM/RLM."""
    if not s:
        return s or ""
    return (
        s.replace("*", "")
         .replace("\u200e", "")
         .replace("\u200f", "")
         .strip()
    )

# ---------------- normalizadores/calculadores ----------------
def _smart_name_capitalize(s: str) -> str:
    if not s:
        return s
    particles = {"de", "del", "la", "las", "los", "y", "da", "das", "di", "van", "von"}
    tokens = [t for t in re.split(r"\s+", s.strip()) if t]

    def cap_token(tok: str) -> str:
        def cap_simple(w: str) -> str:
            return w[:1].upper() + w[1:].lower() if w else w
        w = "'".join(cap_simple(p) for p in tok.split("'"))
        return "-".join(cap_simple(p) for p in w.split("-"))

    out = []
    for i, t in enumerate(tokens):
        out.append(t.lower() if (i > 0 and t.lower() in particles) else cap_token(t))
    return " ".join(out)

def _norm_year(y: int) -> int:
    if y < 100:
        return (2000 if y <= 21 else 1900) + y
    return y

def _parse_date_ddmmyyyy(s: str) -> Optional[str]:
    try:
        d, m, y = s.split("/")
        y = int(y)
        if y < 1900:
            return None
        dt = date(int(y), int(m), int(d))
        if dt > date.today():
            return None
        return f"{int(d):02d}/{int(m):02d}/{int(y):04d}"
    except Exception:
        return None

def _calc_edad(fecha_nac_ddmmyyyy: Optional[str]) -> Optional[int]:
    if not fecha_nac_ddmmyyyy:
        return None
    try:
        d, m, y = map(int, fecha_nac_ddmmyyyy.split("/"))
        born = date(y, m, d)
        today = date.today()
        years = today.year - born.year - ((today.month, today.day) < (born.month, born.day))
        return max(0, years)
    except Exception:
        return None

def _calc_imc(peso_kg: Optional[float], talla_cm: Optional[int]) -> Optional[float]:
    try:
        if not peso_kg or not talla_cm:
            return None
        m = talla_cm / 100.0
        if m <= 0:
            return None
        return round(peso_kg / (m * m), 1)
    except Exception:
        return None

# ---------------- Heurística rápida para motivo ----------------
def normalize_motivo_clinico_heuristic(raw: Optional[str]) -> Optional[str]:
    if not raw:
        return None
    s = raw.lower().strip()
    rules = [
        (r"apend", "apendicectomía"),
        (r"ves[ií]cul|colecist", "colecistectomía"),
        (r"\bhernia\s*(?:inguinal|ingle)\b", "hernioplastia inguinal"),
        (r"\bhernia\s*(?:umbilical|omblig)\b", "hernioplastia umbilical"),
        (r"\bhernia\s*(?:hiatal|hiato)\b", "hernioplastia hiatal"),
        (r"\bhernia\s*(?:crural|femoral)\b", "hernioplastia crural"),
        (r"catarat", "facoemulsificación de catarata"),
        (r"rinoplast", "rinoplastia"),
        (r"nariz", "rinoplastia"),
        (r"quiste", "quistectomía"),
        (r"mama.*(tumor|n[óo]dulo)", "tumorectomía de mama"),
        (r"mastect", "mastectomía"),
    ]
    for pat, term in rules:
        if re.search(pat, s):
            return term
    return raw.strip().capitalize()

# ---------------- Módulo 0: DATOS GENERALES ----------------
def _parse_generales(text: str) -> Dict[str, Any]:
    # 0) Normalización de markup (negritas, invisibles)
    raw_text = text or ""
    text = _strip_whatsapp_markup(raw_text)

    greeted = bool(_GREETING_RE.search(text.strip()))

    # 1) Etiquetas (con el texto ya sin asteriscos)
    nombre = (_RE_NOMBRE.search(text) or [None, None])[1]
    dni_raw = (_RE_DNI_LABELED.search(text) or [None, None])[1]
    fnac = (_RE_FNAC.search(text) or [None, None])[1]
    peso_s = (_RE_PESO.search(text) or [None, None])[1]
    talla_s = (_RE_TALLA.search(text) or [None, None])[1]
    os_ = (_RE_OS.search(text) or [None, None])[1]
    afiliado = (_RE_AFIL.search(text) or [None, None])[1]
    motivo = (_RE_MOTIVO.search(text) or [None, None])[1]

    # 2) Fallback libre
    if not nombre:
        m = _NAME_FREE_RE.search(text)
        if m:
            tmp = " ".join(m.group("nombre").split())
            tmp = re.sub(r"^\s*y\s+apellido\s*:\s*", "", tmp, flags=re.IGNORECASE)
            nombre = tmp
    if not dni_raw:
        m = _DNI_FREE_RE.search(text)
        if m: dni_raw = m.group("dni")
    if not fnac:
        m = _DOB_FREE_RE.search(text)
        if m:
            d = int(m.group("d")); mth = int(m.group("m")); y = _norm_year(int(m.group("y")))
            fnac = f"{d:02d}/{mth:02d}/{y:04d}"
    if not peso_s:
        m = _WEIGHT_FREE_RE.search(text)
        if m: peso_s = m.group("peso")
    if not talla_s:
        m = _HEIGHT_FREE_CM_RE.search(text)
        if m:
            talla_s = m.group("talla")
        else:
            m2 = _HEIGHT_FREE_M_RE.search(text)
            if m2:
                try:
                    metros = float(m2.group("metros").replace(",", "."))
                    talla_s = str(metros)  # en metros, normalizamos abajo
                except Exception:
                    pass
    if not os_:
        m = _OS_FREE_RE.search(text)
        if m: os_ = m.group("os").strip()
    if not afiliado:
        m = _AFIL_FREE_RE.search(text)
        if m: afiliado = m.group("afil").strip()
    if not motivo:
        m = _MOTIVO_FREE_RE.search(text)
        if m: motivo = m.group("motivo").strip()

    # Si solo fue un saludo y no se extrajo nada, devolver _start
    if greeted and not any([nombre, dni_raw, fnac, peso_s, talla_s, os_, afiliado, motivo]):
        return {"_start": True}

    # 3) Normalizaciones/validaciones
    out_dni: Optional[str] = None
    if dni_raw:
        cleaned = re.sub(r"[.\s]", "", dni_raw).lstrip("0") or "0"
        if cleaned.isdigit() and 6 <= len(cleaned) <= 10:
            out_dni = cleaned

    fnac_std = _parse_date_ddmmyyyy(fnac) if fnac else None

    peso: Optional[float] = None
    if peso_s:
        try:
            peso = float(peso_s.replace(",", "."))
            if not (20 <= peso <= 300): peso = None
        except Exception:
            peso = None

    talla: Optional[int] = None
    if talla_s:
        try:
            ss = talla_s.strip().replace(",", ".")
            val = float(ss)
            if 0.9 <= val <= 2.5:
                t = int(round(val * 100))   # metros -> cm
            else:
                t = int(round(val))         # ya en cm
            if 100 <= t <= 230:
                talla = t
        except Exception:
            talla = None

    os_val = (os_ or "").strip(" -:") or None
    afiliado_val = (afiliado or "").strip() or None
    motivo_val = (motivo or "").strip()[:200] if motivo else None

    today = date.today()
    feval_std = f"{today.day:02d}/{today.month:02d}/{today.year:04d}"

    edad = _calc_edad(fnac_std)
    imc = _calc_imc(peso, talla)

    ficha: Dict[str, Any] = {}
    if out_dni: ficha["dni"] = out_dni

    datos: Dict[str, Any] = {}
    if nombre:
        nombre_cap = _smart_name_capitalize(nombre)
        if not re.fullmatch(r"y\s+apellido\s*:?", nombre_cap, flags=re.IGNORECASE):
            datos["nombre_completo"] = nombre_cap
    if fnac_std: datos["fecha_nacimiento"] = fnac_std
    if edad is not None: datos["edad"] = edad
    datos["fecha_evaluacion"] = feval_std
    if datos: ficha["datos"] = datos

    antropo: Dict[str, Any] = {}
    if peso is not None: antropo["peso_kg"] = peso
    if talla is not None: antropo["talla_cm"] = talla
    if imc is not None: antropo["imc"] = imc
    if antropo: ficha["antropometria"] = antropo

    motivo_norm = normalize_motivo_clinico_heuristic(motivo_val) if motivo_val else None

    cobertura: Dict[str, Any] = {}
    if os_val: cobertura["obra_social"] = os_val
    if afiliado_val: cobertura["afiliado"] = afiliado_val
    if motivo_norm: cobertura["motivo_cirugia"] = motivo_norm
    if cobertura: ficha["cobertura"] = cobertura

    return {"ficha": ficha} if ficha else {}

# ---------------- Parsers por módulo ----------------
_ALERG_RE_FREE = re.compile(r"(?:alergias?|al[ée]rgico[as]?)\b[:\s-]*([^\n]+)", re.IGNORECASE)
_NO_ALERG_RE = re.compile(r"\b(no|ninguna?)\b.*\b(alergia|alergias)\b", re.IGNORECASE)

_MEDIC_RE_FREE = re.compile(
    r"(?:medicaci[oó]n|tomo|tomas|toma|puff|inhalador(?:es)?)\b[:\s-]*([^\n]+)",
    re.IGNORECASE
)

def _parse_alergias(text: str) -> Dict[str, Any]:
    s = (text or "").strip()
    if not s:
        return {}
    out: Dict[str, Any] = {}
    if _NO_ALERG_RE.search(s):
        out = {
            "alergia_medicacion": {
                "alergias": {
                    "tiene_alergias": False,
                    "detalle": []
                }
            }
        }
        return {"ficha": out}

    m = _ALERG_RE_FREE.search(s)
    if m:
        detalle_txt = m.group(1).strip()
        if detalle_txt:
            out = {
                "alergia_medicacion": {
                    "alergias": {
                        "tiene_alergias": True,
                        "detalle": [{"sustancia": detalle_txt}]
                    }
                }
            }
    return {"ficha": out} if out else {}

def _parse_medicacion(text: str) -> Dict[str, Any]:
    s = (text or "").strip()
    if not s:
        return {}
    out: Dict[str, Any] = {}
    m = _MEDIC_RE_FREE.search(s)
    if m:
        meds = m.group(1).strip()
        if meds:
            out = {
                "alergia_medicacion": {
                    "medicacion_habitual": [{"droga": meds}]
                }
            }
    return {"ficha": out} if out else {}

def _parse_antecedentes(text: str) -> Dict[str, Any]:
    _ANTEC_RE = re.compile(r"(?:antecedentes?|enfermedades?|patolog[ií]a?s?)\s*:?\s*[- ]*(?P<antecedentes>.+)", re.IGNORECASE)
    m = _ANTEC_RE.search(text or "")
    if not m: return {}
    return {"ficha": {"antecedentes": {"otros": [m.group("antecedentes").strip()]}}}

def _parse_complementarios(text: str) -> Dict[str, Any]:
    _COMPL_RE = re.compile(r"(?:estudios?|laboratorio|lab[s]?|electro|ecg|rx|placa|tc|mri|rmn)\s*:?\s*[- ]*(?P<complementarios>.+)", re.IGNORECASE)
    m = _COMPL_RE.search(text or "")
    if not m: return {}
    return {"ficha": {"complementarios": {"imagenes": [{"estudio": m.group("complementarios").strip()}]}}}

def _parse_sustancias(text: str) -> Dict[str, Any]:
    _TABA_RE = re.compile(r"(?:tabaco|fumo|fum[oé]s?|cigarrillos?)\s*:?\s*[- ]*(?P<tabaco>.+)", re.IGNORECASE)
    _ALCO_RE = re.compile(r"(?:alcohol|beb[eo]s?)\s*:?\s*[- ]*(?P<alcohol>.+)", re.IGNORECASE)
    _OTRAS_RE = re.compile(r"(?:drogas?|sustancias?)\s*:?\s*[- ]*(?P<otras>.+)", re.IGNORECASE)

    out: Dict[str, Any] = {}
    mt = _TABA_RE.search(text or "")
    if mt:
        out.setdefault("sustancias", {})
        out["sustancias"]["tabaco"] = {"consume": True, "ultimo_consumo": mt.group("tabaco").strip()}
    ma = _ALCO_RE.search(text or "")
    if ma:
        out.setdefault("sustancias", {})
        out["sustancias"]["alcohol"] = {"consume": True}
    mo = _OTRAS_RE.search(text or "")
    if mo:
        out.setdefault("sustancias", {})
        out["sustancias"]["otras"] = {"consume": True, "detalle": [mo.group("otras").strip()]}
    return {"ficha": out} if out else {}

def _parse_via_aerea(text: str) -> Dict[str, Any]:
    _VA_RE = re.compile(r"(?:v[ií]a\s*a[ée]rea|mallampati|apertura|bucal|dentari[ao]s?|piezas|pr[oó]tesis)\s*:?\s*[- ]*(?P<via_aerea>.+)", re.IGNORECASE)
    m = _VA_RE.search(text or "")
    if not m: return {}
    return {"ficha": {"via_aerea": {"otros": [m.group("via_aerea").strip()]}}}

_PARSERS = {
    0: _parse_generales,
    1: _parse_alergias,          # NUEVO módulo 1
    2: _parse_medicacion,        # NUEVO módulo 2
    3: _parse_antecedentes,
    4: _parse_complementarios,
    5: _parse_sustancias,
    6: _parse_via_aerea,
}

def fill_from_text_modular(state: Any, module_idx: int, text: str) -> Dict[str, Any]:
    parser = _PARSERS.get(module_idx)
    if not parser: return {}
    data = parser(text or "")
    return data or {}

# ============================================================================
# LLM extractores
# ============================================================================
def _call_openai(messages: list[dict], max_tokens: int = 128) -> Optional[str]:
    """Intenta llamar OpenAI por SDK v1 o v0; devuelve el texto o None."""
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return None
    model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    try:
        # nuevo SDK
        from openai import OpenAI
        client = OpenAI(api_key=api_key)
        rsp = client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=0,
            max_tokens=max_tokens,
        )
        return (rsp.choices[0].message.content or "").strip()
    except Exception:
        try:
            # compat SDK antiguo
            import openai  # type: ignore
            openai.api_key = api_key
            rsp = openai.ChatCompletion.create(
                model=model,
                messages=messages,
                temperature=0,
                max_tokens=max_tokens,
            )
            return (rsp["choices"][0]["message"]["content"] or "").strip()
        except Exception:
            return None

# ---- LLM: Generales (ya existente) ----
def _llm_extract_generales_full(text: str) -> Dict[str, Any]:
    """Extractor LLM para respuestas libres del Módulo 0."""
    if not (text or "").strip():
        return {}

    system = (
        "Sos un extractor de datos para admisión preanestésica en Argentina. "
        "Debés leer un mensaje libre de WhatsApp y devolver SOLO un JSON válido con este esquema:"
        '{"nombre_apellido":{"value":null,"source_span":null,"confidence":0.0},"dni":{"value":null,"source_span":null,"confidence":0.0},"fecha_nacimiento":{"value":null,"source_span":null,"confidence":0.0},"peso_kg":{"value":null,"source_span":null,"confidence":0.0},"talla_cm":{"value":null,"source_span":null,"confidence":0.0},"obra_social":{"value":null,"source_span":null,"confidence":0.0},"nro_afiliado":{"value":null,"source_span":null,"confidence":0.0},"motivo_consulta":{"value":null,"source_span":null,"confidence":0.0},"imc":{"value":null},"missing_fields":[],"questions_to_user":[]}'
        " Reglas: DNI solo dígitos; fecha en dd/mm/aaaa; talla en cm; calcular IMC si hay peso y talla. "
        "Si un dato es imposible, dejalo en null."
    )
    user = f"Mensaje del paciente:\n{text}"

    try:
        from core.llm_client import llm_client  # type: ignore
        raw = llm_client.call_llm_simple(
            prompt=system + "\n\n" + user, max_tokens=350, temperature=0
        )
    except Exception:
        raw = _call_openai(
            messages=[{"role": "system", "content": system},
                      {"role": "user", "content": user}], max_tokens=350
        )
    if not raw:
        return {}

    try:
        obj = json.loads(raw)
    except Exception:
        return {}

    def _getv(key: str):
        it = obj.get(key) or {}
        return (it.get("value") if isinstance(it, dict) else None)

    nombre = (_getv("nombre_apellido") or "").strip()
    dni_raw = (_getv("dni") or "").strip()
    fnac = (_getv("fecha_nacimiento") or "").strip()
    peso = _getv("peso_kg")
    talla = _getv("talla_cm")
    os_ = (_getv("obra_social") or "").strip()
    afiliado = (_getv("nro_afiliado") or "").strip()
    motivo = (_getv("motivo_consulta") or "").strip()
    imc_val = obj.get("imc", {}).get("value") if isinstance(obj.get("imc"), dict) else obj.get("imc")

    dni = re.sub(r"\D+", "", dni_raw) if dni_raw else None
    if dni and not (6 <= len(dni) <= 10):
        dni = None

    fnac_std = _parse_date_ddmmyyyy(fnac) if fnac else None

    try:
        peso_f = float(str(peso).replace(",", ".")) if peso is not None else None
        if peso_f is not None and not (20 <= peso_f <= 300):
            peso_f = None
    except Exception:
        peso_f = None

    try:
        if talla is None:
            talla_cm = None
        else:
            tv = float(str(talla).replace(",", "."))
            if 0.9 <= tv <= 2.5:
                talla_cm = int(round(tv * 100))
            else:
                talla_cm = int(round(tv))
            if not (100 <= talla_cm <= 230):
                talla_cm = None
    except Exception:
        talla_cm = None

    if imc_val is None:
        imc_val = _calc_imc(peso_f, talla_cm)

    motivo_norm = normalize_motivo_clinico_heuristic(motivo) if motivo else None

    today = date.today()
    feval_std = f"{today.day:02d}/{today.month:02d}/{today.year:04d}"
    edad = _calc_edad(fnac_std)

    ficha: Dict[str, Any] = {}
    if dni: ficha["dni"] = dni

    datos: Dict[str, Any] = {}
    if nombre:
        nombre_cap = _smart_name_capitalize(nombre)
        if not re.fullmatch(r"y\s+apellido\s*:?", nombre_cap, flags=re.IGNORECASE):
            datos["nombre_completo"] = nombre_cap
    if fnac_std: datos["fecha_nacimiento"] = fnac_std
    if edad is not None: datos["edad"] = edad
    datos["fecha_evaluacion"] = feval_std
    if datos: ficha["datos"] = datos

    antropo: Dict[str, Any] = {}
    if peso_f is not None: antropo["peso_kg"] = peso_f
    if talla_cm is not None: antropo["talla_cm"] = talla_cm
    if imc_val is not None: antropo["imc"] = imc_val
    if antropo: ficha["antropometria"] = antropo

    cobertura: Dict[str, Any] = {}
    if os_: cobertura["obra_social"] = os_
    if afiliado: cobertura["afiliado"] = afiliado
    if motivo_norm: cobertura["motivo_cirugia"] = motivo_norm
    if cobertura: ficha["cobertura"] = cobertura

    return {"ficha": ficha} if ficha else {}

# ---- LLM: Alergias (módulo 1) ----
def _llm_extract_alergias(text: str) -> Dict[str, Any]:
    """
    Devuelve:
    {
      "tiene_alergias": true/false,
      "detalles": [{"sustancia": str, "reaccion": str|null}, ...]
    }
    """
    if not (text or "").strip():
        return {}
    system = (
        "Sos un extractor clínico. A partir de un texto libre en español, devolvé SOLO JSON con este esquema: "
        '{"tiene_alergias": bool, "detalles": [{"sustancia": str, "reaccion": str|null}]}. '
        "Considerá alergias a comidas, fármacos, látex y otras. Si el paciente niega, usá tiene_alergias=false y detalles=[]. "
        "Si describe síntomas (rash/ronchas, edema, broncoespasmo, anafilaxia/shock, picazón, etc.), ponelos en 'reaccion'."
    )
    user = f"Texto del paciente:\n{text}"
    raw = _call_openai(
        messages=[{"role": "system", "content": system},
                  {"role": "user", "content": user}],
        max_tokens=250
    )
    try:
        obj = json.loads(raw) if raw else {}
    except Exception:
        obj = {}
    if not isinstance(obj, dict):
        return {}

    tiene = bool(obj.get("tiene_alergias", False))
    detalles = obj.get("detalles") or []
    norm_detalles = []
    for it in detalles:
        if not isinstance(it, dict): continue
        sust = (it.get("sustancia") or "").strip()
        reac = (it.get("reaccion") or None)
        if sust:
            norm_detalles.append({"sustancia": sust, "reaccion": (reac or None)})
    return {
        "ficha": {
            "alergia_medicacion": {
                "alergias": {
                    "tiene_alergias": tiene,
                    "detalle": norm_detalles
                }
            }
        }
    }

# ---- LLM: Medicación (módulo 2) ----
def _llm_extract_medicacion(text: str) -> Dict[str, Any]:
    """
    Devuelve lista normalizada de medicamentos:
    [{"droga": principio_activo_o_nombre, "dosis": "10 mg", "frecuencia": "cada 12 h"}]
    Acepta nombres comerciales e intenta mapear al principio activo.
    Incluye puff/inhaladores.
    """
    if not (text or "").strip():
        return {}
    system = (
        "Sos un normalizador de medicación. A partir de un texto en español con medicación habitual, "
        "devolvé SOLO JSON con este esquema: "
        '{"meds":[{"droga": str, "dosis": str|null, "frecuencia": str|null}]} '
        "Aceptá nombres comerciales (mapear al principio activo cuando sea posible) y también inhaladores/puff. "
        "Si no hay medicación, usá meds=[]. No inventes dosis."
    )
    user = f"Texto del paciente:\n{text}"
    raw = _call_openai(
        messages=[{"role": "system", "content": system},
                  {"role": "user", "content": user}],
        max_tokens=300
    )
    try:
        obj = json.loads(raw) if raw else {}
    except Exception:
        obj = {}
    meds_in = obj.get("meds") or []
    meds_out = []
    for it in meds_in:
        if not isinstance(it, dict): continue
        d = (it.get("droga") or "").strip()
        if not d: continue
        dosis = (it.get("dosis") or None)
        frec = (it.get("frecuencia") or None)
        meds_out.append({"droga": d, "dosis": dosis, "frecuencia": frec})
    return {"ficha": {"alergia_medicacion": {"medicacion_habitual": meds_out}}}

# ============================================================================
# LLM: normalización por módulo
# ============================================================================
def llm_parse_modular(text: str, module_idx: int) -> Dict[str, Any]:
    if module_idx == 0:
        patch_total: Dict[str, Any] = {}

        patch_free = _llm_extract_generales_full(text or "")
        if patch_free:
            patch_total = _deep_merge_dict(patch_total, patch_free)

        # Normalización SNOMED opcional (best-effort)
        m = re.search(r"(?im)^motivo.*?:\s*(.+)$", text or "")
        candidate = (m.group(1).strip() if m else None) or ""
        if not candidate:
            m2 = re.search(
                r"(oper(ar|aci[oó]n)|sac(ar|an)|extirpar|quitar|me\s+hacen|intervenci[oó]n)[:\s,-]*([^\n]+)",
                text or "", re.IGNORECASE)
            if m2:
                candidate = (m2.group(4) or "").strip()

        if candidate:
            system = (
                "Eres un codificador clínico experto en procedimientos quirúrgicos. "
                "Estandariza descripciones libres en español a un término/procedimiento SNOMED CT. "
                "Responde SOLO en JSON: {\"term_es\": str, \"sctid\": str|null, \"fsn_en\": str|null, \"confidence\": num}."
            )
            user = (
                "Texto del paciente (español):\n"
                f"{text}\n\n"
                f"Motivo libre detectado: {candidate}"
            )
            raw = _call_openai(
                messages=[{"role": "system", "content": system},
                          {"role": "user", "content": user}],
                max_tokens=200,
            )
            if raw:
                try:
                    obj = json.loads(raw)
                    term_es = (obj.get("term_es") or "").strip() or None
                    sctid = (obj.get("sctid") or None)
                    fsn = (obj.get("fsn_en") or None)
                    conf = float(obj.get("confidence") or 0)
                except Exception:
                    term_es = raw.strip() if raw else None
                    sctid = fsn = None
                    conf = 0.0

                if term_es:
                    term_es = re.sub(r"[^A-Za-zÁÉÍÓÚÜÑáéíóúüñ\s\-]", "", term_es).strip()
                    patch_sn = {}
                    if conf >= 0.65 or sctid:
                        patch_sn = {"ficha": {"cobertura": {"motivo_cirugia": term_es}}}
                    if sctid or fsn:
                        patch_sn.setdefault("ficha", {}).setdefault("cobertura", {})["motivo_snomed"] = {
                            "sctid": sctid, "fsn_en": fsn, "confidence": conf
                        }
                    patch_total = _deep_merge_dict(patch_total, patch_sn)

        return patch_total

    if module_idx == 1:  # Alergias
        return _llm_extract_alergias(text or "")

    if module_idx == 2:  # Medicación habitual
        return _llm_extract_medicacion(text or "")

    return {}

# ============================================================================
# Confirmación (solo campos presentes)
# ============================================================================
def _fmt(v: Any) -> Optional[str]:
    return None if v in (None, "", []) else str(v)

def summarize_patch_for_confirmation(patch: Dict[str, Any], module_idx: int) -> str:
    ficha = patch.get("ficha", patch) or {}
    if not isinstance(ficha, dict):
        return ""

    if module_idx == 0 and "_start" in ficha and len(ficha) == 1:
        return "¡Hola! Empecemos."

    if module_idx == 0:
        dni = ficha.get("dni")
        datos = ficha.get("datos", {}) if isinstance(ficha.get("datos"), dict) else {}
        antropo = ficha.get("antropometria", {}) if isinstance(ficha.get("antropometria"), dict) else {}
        cob = ficha.get("cobertura", {}) if isinstance(ficha.get("cobertura"), dict) else {}

        nombre = datos.get("nombre_completo")
        fnac = datos.get("fecha_nacimiento")
        edad = datos.get("edad")
        peso = antropo.get("peso_kg")
        talla = antropo.get("talla_cm")
        imc = antropo.get("imc")
        os_ = cob.get("obra_social")
        afil = cob.get("afiliado")
        motivo = cob.get("motivo_cirugia")

        lines = []
        if any([nombre, dni, fnac, edad, peso, talla, imc, os_, afil, motivo]):
            lines.append("✔️ Registré:")
        if _fmt(nombre) or _fmt(dni):
            left = _fmt(nombre) or ""
            right = f"DNI {dni}" if _fmt(dni) else ""
            lines.append(f"• {left}{(' — ' + right) if left and right else right}")
        if _fmt(fnac) or _fmt(edad):
            left = _fmt(fnac) or ""
            right = f"({_fmt(edad)} años)" if _fmt(edad) else ""
            lines.append(f"• Nac.: {left} {right}".strip())
        if _fmt(peso) or _fmt(talla) or _fmt(imc):
            parts = []
            if _fmt(peso): parts.append(f"Peso {peso} kg")
            if _fmt(talla): parts.append(f"Talla {talla} cm")
            if _fmt(imc): parts.append(f"IMC {imc}")
            lines.append(f"• " + ", ".join(parts))
        if _fmt(os_) or _fmt(afil):
            parts = []
            if _fmt(os_): parts.append(f"Obra social: {os_}")
            if _fmt(afil): parts.append(f"Afiliado: {afil}")
            lines.append("• " + " — ".join(parts))
        if _fmt(motivo):
            lines.append(f"• Motivo: {motivo}")

        return "\n".join([l for l in lines if l])

    # Confirmación específica por módulo
    if module_idx == 1:  # Alergias
        am = ficha.get("alergia_medicacion", {}) if isinstance(ficha.get("alergia_medicacion"), dict) else {}
        alg = am.get("alergias", {}) if isinstance(am.get("alergias"), dict) else {}
        tiene = alg.get("tiene_alergias")
        detalles = alg.get("detalle") or []
        if tiene is False:
            return "✔️ Registré: sin alergias conocidas."
        if detalles:
            lines = ["✔️ Alergias:"]
            for d in detalles:
                if not isinstance(d, dict): continue
                sust = d.get("sustancia"); reac = d.get("reaccion")
                if sust and reac:
                    lines.append(f"• {sust}: {reac}")
                elif sust:
                    lines.append(f"• {sust}")
            return "\n".join(lines)
        return ""

    if module_idx == 2:  # Medicación
        am = ficha.get("alergia_medicacion", {}) if isinstance(ficha.get("alergia_medicacion"), dict) else {}
        meds = am.get("medicacion_habitual") or []
        if meds:
            lines = ["✔️ Medicación habitual:"]
            for m in meds:
                if not isinstance(m, dict): continue
                droga = m.get("droga"); dosis = m.get("dosis"); frec = m.get("frecuencia")
                if not droga: continue
                extra = " ".join(x for x in [dosis or "", f"({frec})" if frec else ""] if x).strip()
                lines.append(f"• {droga}" + (f" — {extra}" if extra else ""))
            return "\n".join(lines)
        return ""

    public_items = [(k, v) for k, v in ficha.items() if not str(k).startswith("_")]
    if not public_items:
        return ""
    modulo_name = MODULES[module_idx]["name"] if 0 <= module_idx < len(MODULES) else "Bloque"
    joined = "; ".join(f"{k}: {v}" for k, v in public_items)
    return f"Anoté en {modulo_name}: {joined}."
