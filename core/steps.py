from __future__ import annotations

from typing import Any, Dict, Optional, Tuple, get_origin, get_args
from pydantic import BaseModel
import re
import os
import json
from datetime import date

# ========================== MÓDULOS ==========================
MODULES = [
    {
        "name": "Datos generales",
        "use_llm": True,
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
            "¿Sos alérgico a alguna medicación o comida?\n"
            "Si la tenés, contame *a qué* y *qué te pasó* en tus palabras (ej: ronchas/rash, "
            "hinchazón, falta de aire, picazón, shock). Si no, decí: \"no alergias conocidas\"."
        ),
    },
    {
        "name": "Medicación habitual",
        "use_llm": True,
        # PRIMERA PREGUNTA del módulo 2 (solo medicación)
        "prompt": (
            "¿Tomás alguna medicación / usás puff?\n"
            "Si sabés la *dosis*, mejor.\n"
            "\n"
            "_Ejemplos: \"Enalapril 10 mg cada mañana\", \"Sertal\", \"Seretide puff 2 veces al día\"._"
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

# SEGUNDA PREGUNTA del módulo 2 (ilícitas)
PROMPT_ILICITAS_M2 = (
    "¿Consumís *sustancias ilícitas* (p. ej. cannabis/porro/faso, cocaína, MDMA/éxtasis, "
    "ketamina, LSD, paco, hongos/psilocibina, tusi, etc.)?\n"
    "Si sí, contá *cuál*, *frecuencia/cantidad* y *cuándo fue la última vez*."
)

# =================== Helpers de estado y merge ===================
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

# ================== Regex & parsers Módulo 0 ==================
_RE_FLAGS = re.IGNORECASE | re.MULTILINE
_RE_NOMBRE = re.compile(r"^nombre y apellido:\s*([A-Za-zÁÉÍÓÚÜÑñ'´`\- ]{3,}(?:\s+[A-Za-zÁÉÍÓÚÜÑñ'´`\- ]{2,})+)\s*$", _RE_FLAGS)
_RE_DNI_LABELED = re.compile(r"^dni.*?:\s*([0-9][0-9.\s]{5,})$", _RE_FLAGS)
_RE_FNAC = re.compile(r"^fecha nacimiento.*?:\s*(\d{1,2}/\d{1,2}/\d{4})$", _RE_FLAGS)
_RE_PESO = re.compile(r"^peso.*?kg.*?:\s*([0-9]{1,3}(?:[.,][0-9]{1,2})?)$", _RE_FLAGS)
_RE_TALLA = re.compile(r"^talla.*?:\s*([0-9]{1,3}(?:[.,][0-9]{1,2})?)$", _RE_FLAGS)
_RE_OS = re.compile(r"^obra social:\s*([A-Za-zÁÉÍÓÚÜÑñ0-9 .,'\-]{2,60})$", _RE_FLAGS)
_RE_AFIL = re.compile(r"^(?:n°|nº|num(?:ero)?)[\s_-]*afiliad[oa]:\s*([A-Za-z0-9\-./]{3,30})$", _RE_FLAGS)
_RE_MOTIVO = re.compile(r"^motivo.*?:\s*(.{3,200})$", _RE_FLAGS)

_GREETING_RE = re.compile(r"^\s*(hola|buenas|hey|hi|qué\s*tal|buen\s*d[ií]a|buenas\s*tardes|buenas\s*noches)\b", re.IGNORECASE)
_DNI_FREE_RE = re.compile(r"\b(?P<dni>\d{6,10})\b")
_NAME_FREE_RE = re.compile(r"(?:me\s+llamo|soy|nombre(?:\s+y\s+apellido)?\s*:?\s*)(?P<nombre>[\wÀ-ÿ'´`\- ]{3,})", re.IGNORECASE)
_DOB_FREE_RE = re.compile(r"\b(?P<d>\d{1,2})[/-](?P<m>\d{1,2})[/-](?P<y>\d{2,4})\b")
_WEIGHT_FREE_RE = re.compile(r"(?:peso|pesa|kg)\D{0,5}(?P<peso>\d{1,3}(?:[.,]\d{1,2})?)", re.IGNORECASE)
_HEIGHT_FREE_CM_RE = re.compile(r"(?:mido|talla|altura|cm|mts?|metros?)\D{0,5}(?P<talla>\d{2,3})(?:[.,]\d+)?", re.IGNORECASE)
_HEIGHT_FREE_M_RE = re.compile(r"\b(?P<metros>1(?:[.,]\d{1,2})|0[.,]\d{1,2})\s*m\b", re.IGNORECASE)
_OS_FREE_RE = re.compile(r"(?:obra\s+social|prepaga|cobertura)\s*:?\s*[- ]*(?P<os>[A-Za-zÀ-ÿ0-9\. '\-]{2,})", re.IGNORECASE)
_AFIL_FREE_RE = re.compile(r"(?:nro?\.?\s*afiliad[oa]|afiliad[oa])\s*:?\s*[- ]*(?P<afil>[A-Za-z0-9\-\.\/]{3,})", re.IGNORECASE)
_MOTIVO_FREE_RE = re.compile(r"(?:motivo|cirug[ií]a|procedimiento)\s*:?\s*[- ]*(?P<motivo>[\wÀ-ÿ0-9,\. '\-]{3,})", re.IGNORECASE)

def _strip_whatsapp_markup(s: str) -> str:
    if not s:
        return s or ""
    return s.replace("*", "").replace("\u200e", "").replace("\u200f", "").strip()

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
    return (2000 if y < 100 and y <= 21 else (1900 if y < 100 else 0)) + (y if y >= 100 else y)

def _parse_date_ddmmyyyy(s: str) -> Optional[str]:
    try:
        d, m, y = s.split("/")
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
        return today.year - born.year - ((today.month, today.day) < (born.month, born.day))
    except Exception:
        return None

def _calc_imc(peso_kg: Optional[float], talla_cm: Optional[int]) -> Optional[float]:
    try:
        if not peso_kg or not talla_cm:
            return None
        m = talla_cm / 100.0
        return round(peso_kg / (m * m), 1)
    except Exception:
        return None

# Heurística rápida de motivo
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
        (r"catarat", "facoemulsificación de catarata"),
        (r"rinoplast|nariz", "rinoplastia"),
        (r"quiste", "quistectomía"),
    ]
    for pat, term in rules:
        if re.search(pat, s):
            return term
    return raw.strip().capitalize()

# ================== Módulo 0: DATOS GENERALES ==================
def _parse_generales(text: str) -> Dict[str, Any]:
    text = _strip_whatsapp_markup(text or "")
    greeted = bool(_GREETING_RE.search(text.strip()))
    nombre = (_RE_NOMBRE.search(text) or [None, None])[1]
    dni_raw = (_RE_DNI_LABELED.search(text) or [None, None])[1]
    fnac = (_RE_FNAC.search(text) or [None, None])[1]
    peso_s = (_RE_PESO.search(text) or [None, None])[1]
    talla_s = (_RE_TALLA.search(text) or [None, None])[1]
    os_ = (_RE_OS.search(text) or [None, None])[1]
    afiliado = (_RE_AFIL.search(text) or [None, None])[1]
    motivo = (_RE_MOTIVO.search(text) or [None, None])[1]

    if greeted and not any([nombre, dni_raw, fnac, peso_s, talla_s, os_, afiliado, motivo]):
        return {"_start": True}

    if not nombre:
        m = _NAME_FREE_RE.search(text)
        if m: nombre = " ".join(m.group("nombre").split())
    if not dni_raw:
        m = _DNI_FREE_RE.search(text)
        if m: dni_raw = m.group("dni")
    if not fnac:
        m = _DOB_FREE_RE.search(text)
        if m:
            d = int(m.group("d")); mm = int(m.group("m")); yy = int(m.group("y")); yy = _norm_year(yy)
            fnac = f"{d:02d}/{mm:02d}/{yy:04d}"
    if not peso_s:
        m = _WEIGHT_FREE_RE.search(text)
        if m: peso_s = m.group("peso")
    if not talla_s:
        m = _HEIGHT_FREE_CM_RE.search(text) or _HEIGHT_FREE_M_RE.search(text)
        if m: talla_s = m.groupdict().get("talla") or m.groupdict().get("metros")

    dni = None
    if dni_raw:
        cleaned = re.sub(r"[.\s]", "", dni_raw)
        if cleaned.isdigit() and 6 <= len(cleaned) <= 10:
            dni = cleaned
    fnac_std = _parse_date_ddmmyyyy(fnac) if fnac else None

    peso = None
    if peso_s:
        try:
            v = float(str(peso_s).replace(",", "."))
            if 20 <= v <= 300:
                peso = v
        except Exception:
            pass

    talla_cm = None
    if talla_s:
        try:
            v = float(str(talla_s).replace(",", "."))
            talla_cm = int(round(v * 100)) if 0.9 <= v <= 2.5 else int(round(v))
            if not 100 <= talla_cm <= 230:
                talla_cm = None
        except Exception:
            pass

    imc = _calc_imc(peso, talla_cm)
    today = date.today()
    feval_std = f"{today.day:02d}/{today.month:02d}/{today.year:04d}"

    ficha: Dict[str, Any] = {}
    if dni: ficha["dni"] = dni
    datos = {}
    if nombre: datos["nombre_completo"] = _smart_name_capitalize(nombre)
    if fnac_std: datos["fecha_nacimiento"] = fnac_std
    edad = _calc_edad(fnac_std)
    if edad is not None: datos["edad"] = edad
    datos["fecha_evaluacion"] = feval_std
    if datos: ficha["datos"] = datos

    antropo = {}
    if peso is not None: antropo["peso_kg"] = peso
    if talla_cm is not None: antropo["talla_cm"] = talla_cm
    if imc is not None: antropo["imc"] = imc
    if antropo: ficha["antropometria"] = antropo

    if motivo:
        motivo_norm = normalize_motivo_clinico_heuristic(motivo)
        ficha.setdefault("cobertura", {})["motivo_cirugia"] = motivo_norm

    return {"ficha": ficha} if ficha else {}

# ================== Parsers por módulo ==================
_ALERG_RE_FREE = re.compile(r"(?:alergias?|al[ée]rgic[oa]s?)\b[:\s-]*([^\n]+)", re.IGNORECASE)
_NO_ALERG_RE = re.compile(r"\b(no|ninguna?)\b.*\b(alergia|al[ée]rgic[oa]s?)\b", re.IGNORECASE)

_MEDIC_RE_FREE = re.compile(r"(?:medicaci[oó]n|tomo|tomas|toma|puff|inhalador(?:es)?)\b[:\s-]*([^\n]+)", re.IGNORECASE)

# ilícitas (para parser local)
_NEG_ILICIT_RE = re.compile(r"\b(no|nunca)\b.*\b(drogas?|il[ií]citas?|porro|marihuana|cannabis|coca[ií]na|paco|mdma|[ée]xtasis|ketamina|lsd|hongos|tusi)\b", re.IGNORECASE)
_ILICIT_KEYS = [
    "cannabis","marihuana","porro","faso","weed","cocaína","merca","perico",
    "paco","mdma","éxtasis","extasis","ketamina","lsd","ácido","acido","hongos","psilocibina","tusi","2cb","2c-b"
]

def _parse_alergias(text: str) -> Dict[str, Any]:
    s = (text or "").strip()
    if not s:
        return {}
    if _NO_ALERG_RE.search(s):
        return {"ficha": {"alergia_medicacion": {"alergias": {"tiene_alergias": False, "detalle": []}}}}
    m = _ALERG_RE_FREE.search(s)
    if m:
        detalle_txt = m.group(1).strip()
        if detalle_txt:
            return {"ficha": {"alergia_medicacion": {"alergias": {"tiene_alergias": True, "detalle": [{"sustancia": detalle_txt}]}}}}
    return {}

def _parse_medicacion(text: str) -> Dict[str, Any]:
    s = (text or "").strip()
    m = _MEDIC_RE_FREE.search(s)
    if not m:
        return {}
    meds = m.group(1).strip()
    if meds:
        return {"ficha": {"alergia_medicacion": {"medicacion_habitual": [{"droga": meds}]}}}
    return {}

def _parse_ilicitas(text: str) -> Dict[str, Any]:
    s = (text or "").strip().lower()
    if not s:
        return {}
    if _NEG_ILICIT_RE.search(s):
        return {"ficha": {"sustancias": {"ilicitas": {"consume": False, "detalle": []}}}}
    found = []
    for k in _ILICIT_KEYS:
        if re.search(rf"\b{k}\b", s, re.IGNORECASE):
            found.append(k)
    if found:
        return {"ficha": {"sustancias": {"ilicitas": {"consume": True, "detalle": [{"sustancia": x} for x in sorted(set(found))]}}}}
    return {}

def _parse_antecedentes(text: str) -> Dict[str, Any]:
    m = re.search(r"(?:antecedentes?|enfermedades?|patolog[ií]a?s?)\s*:?\s*[- ]*(?P<antecedentes>.+)", text or "", re.IGNORECASE)
    if not m: return {}
    return {"ficha": {"antecedentes": {"otros": [m.group("antecedentes").strip()]}}}

def _parse_complementarios(text: str) -> Dict[str, Any]:
    m = re.search(r"(?:estudios?|laboratorio|lab[s]?|electro|ecg|rx|placa|tc|mri|rmn)\s*:?\s*[- ]*(?P<complementarios>.+)", text or "", re.IGNORECASE)
    if not m: return {}
    return {"ficha": {"complementarios": {"imagenes": [{"estudio": m.group("complementarios").strip()}]}}}

def _parse_sustancias(text: str) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    mt = re.search(r"(?:tabaco|fumo|fum[oé]s?|cigarrillos?)\s*:?\s*[- ]*(?P<tabaco>.+)", text or "", re.IGNORECASE)
    ma = re.search(r"(?:alcohol|beb[eo]s?)\s*:?\s*[- ]*(?P<alcohol>.+)", text or "", re.IGNORECASE)
    mo = re.search(r"(?:drogas?|sustancias?)\s*:?\s*[- ]*(?P<otras>.+)", text or "", re.IGNORECASE)
    if mt: out.setdefault("sustancias", {}); out["sustancias"]["tabaco"] = {"consume": True, "ultimo_consumo": mt.group("tabaco").strip()}
    if ma: out.setdefault("sustancias", {}); out["sustancias"]["alcohol"] = {"consume": True}
    if mo: out.setdefault("sustancias", {}); out["sustancias"]["otras"] = {"consume": True, "detalle": [mo.group("otras").strip()]}
    return {"ficha": out} if out else {}

def _parse_via_aerea(text: str) -> Dict[str, Any]:
    m = re.search(r"(?:v[ií]a\s*a[ée]rea|mallampati|apertura|bucal|dentari[ao]s?|piezas|pr[oó]tesis)\s*:?\s*[- ]*(?P<via_aerea>.+)", text or "", re.IGNORECASE)
    if not m: return {}
    return {"ficha": {"via_aerea": {"otros": [m.group("via_aerea").strip()]}}}

_PARSERS = {0: _parse_generales, 1: _parse_alergias, 2: _parse_medicacion, 3: _parse_antecedentes, 4: _parse_complementarios, 5: _parse_sustancias, 6: _parse_via_aerea}

def fill_from_text_modular(state: Any, module_idx: int, text: str) -> Dict[str, Any]:
    # Manejo de sub-fase del módulo 2 (meds / illicit)
    if module_idx == 2 and getattr(state, "_mod2_phase", "meds") == "illicit":
        return _parse_ilicitas(text or "")
    parser = _PARSERS.get(module_idx)
    if not parser: return {}
    data = parser(text or "")
    return data or {}

# ================== LLM extractores ==================
def _call_openai(messages: list[dict], max_tokens: int = 128) -> Optional[str]:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return None
    model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    try:
        from openai import OpenAI
        client = OpenAI(api_key=api_key)
        rsp = client.chat.completions.create(model=model, messages=messages, temperature=0, max_tokens=max_tokens)
        return (rsp.choices[0].message.content or "").strip()
    except Exception:
        try:
            import openai  # type: ignore
            openai.api_key = api_key
            rsp = openai.ChatCompletion.create(model=model, messages=messages, temperature=0, max_tokens=max_tokens)
            return (rsp["choices"][0]["message"]["content"] or "").strip()
        except Exception:
            return None

def _llm_extract_generales_full(text: str) -> Dict[str, Any]:
    if not (text or "").strip():
        return {}
    system = (
        "Sos un extractor de datos para admisión preanestésica en Argentina. "
        "Devolvé SOLO JSON con este esquema:"
        '{"nombre_apellido":{"value":null},"dni":{"value":null},"fecha_nacimiento":{"value":null},"peso_kg":{"value":null},"talla_cm":{"value":null},"obra_social":{"value":null},"nro_afiliado":{"value":null},"motivo_consulta":{"value":null},"imc":{"value":null}}'
    )
    user = f"Mensaje del paciente:\n{text}"
    raw = _call_openai([{"role":"system","content":system},{"role":"user","content":user}], max_tokens=350)
    if not raw: return {}
    try: obj = json.loads(raw)
    except Exception: return {}

    def _getv(k): 
        it = obj.get(k) or {}
        return (it.get("value") if isinstance(it, dict) else it) or None

    nombre = (_getv("nombre_apellido") or "").strip()
    dni_raw = (_getv("dni") or "").strip()
    fnac = (_getv("fecha_nacimiento") or "").strip()
    peso = _getv("peso_kg")
    talla = _getv("talla_cm")
    os_ = (_getv("obra_social") or "").strip()
    afiliado = (_getv("nro_afiliado") or "").strip()
    motivo = (_getv("motivo_consulta") or "").strip()
    imc_val = _getv("imc")

    dni = re.sub(r"\D", "", dni_raw) if dni_raw else None
    if dni and not (6 <= len(dni) <= 10): dni = None
    fnac_std = _parse_date_ddmmyyyy(fnac) if fnac else None

    try:
        peso_f = float(str(peso).replace(",", ".")) if peso is not None else None
        if peso_f is not None and not (20 <= peso_f <= 300): peso_f = None
    except Exception:
        peso_f = None
    try:
        if talla is None: talla_cm = None
        else:
            tv = float(str(talla).replace(",", "."))
            talla_cm = int(round(tv * 100)) if 0.9 <= tv <= 2.5 else int(round(tv))
            if not (100 <= talla_cm <= 230): talla_cm = None
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
    if nombre: datos["nombre_completo"] = _smart_name_capitalize(nombre)
    if fnac_std: datos["fecha_nacimiento"] = fnac_std
    if edad is not None: datos["edad"] = edad
    datos["fecha_evaluacion"] = feval_std
    if datos: ficha["datos"] = datos
    antropo: Dict[str, Any] = {}
    if peso_f is not None: antropo["peso_kg"] = peso_f
    if talla_cm is not None: antropo["talla_cm"] = talla_cm
    if imc_val is not None: antropo["imc"] = imc_val
    if antropo: ficha["antropometria"] = antropo
    if motivo_norm: ficha.setdefault("cobertura", {})["motivo_cirugia"] = motivo_norm
    return {"ficha": ficha} if ficha else {}

# ---------- Heurística ALERGIAS ----------
_RE_NEG_ALERG = re.compile(r"\b(no|ninguna?)\b.*\b(alergia|al[ée]rgic[oa]s?)\b", re.IGNORECASE)
_RE_RX = [
    (re.compile(r"\bno\s+podi[aá]\s+respirar\b|\bfalta\s+de\s+aire\b|\bdisnea\b", re.IGNORECASE), "falta de aire"),
    (re.compile(r"\b(broncoespasmo|sibilancias?)\b", re.IGNORECASE), "broncoespasmo"),
    (re.compile(r"\brash\b|\bronchas\b|\burticaria\b", re.IGNORECASE), "rash/ronchas"),
    (re.compile(r"\bhinchaz[oó]n\b|\bedema\b|\bangioedema\b", re.IGNORECASE), "hinchazón/edema"),
    (re.compile(r"\bshock\b|\banafilax", re.IGNORECASE), "anafilaxia/shock"),
    (re.compile(r"\bpicaz[oó]n\b|\bprurito\b", re.IGNORECASE), "picazón"),
]

def _heuristic_alergias_from_text(text: str) -> Optional[Dict[str, Any]]:
    s = (text or "").strip()
    if not s:
        return None
    if _RE_NEG_ALERG.search(s):
        return {"tiene_alergias": False, "detalle": []}
    reaction = None
    for rx, label in _RE_RX:
        if rx.search(s):
            reaction = label
            break
    if reaction:
        first = re.split(r"[.,;\n]", s, 1)[0].strip()
        first = re.sub(r"^(soy|era|fui)\s+al[ée]rgic[oa]\s+a\s+", "", first, flags=re.IGNORECASE).strip()
        first = re.sub(r"^a\s+(la|el|los|las)\s+", "", first, flags=re.IGNORECASE).strip()
        sust = first if first else "no especifica"
        return {"tiene_alergias": True, "detalle": [{"sustancia": sust, "reaccion": reaction}]}
    return None

def _llm_extract_alergias(text: str) -> Dict[str, Any]:
    if not (text or "").strip():
        return {}
    heur = _heuristic_alergias_from_text(text)
    if heur is not None:
        return {"ficha": {"alergia_medicacion": {"alergias": {"tiene_alergias": heur["tiene_alergias"], "detalle": heur["detalle"]}}}}

    system = (
        "Sos un extractor clínico de alergias. Devolvé SOLO JSON:\n"
        '{"tiene_alergias": bool, "detalles": [{"sustancia": str, "reaccion": str|null}]}\n'
        "No confundas frases como “no podía respirar” con negación: eso es reacción."
    )
    user = f"Texto del paciente:\n{text}"
    raw = _call_openai([{"role":"system","content":system},{"role":"user","content":user}], max_tokens=250)
    try: obj = json.loads(raw) if raw else {}
    except Exception: obj = {}
    if not isinstance(obj, dict): return {}
    tiene = bool(obj.get("tiene_alergias", False))
    detalles = obj.get("detalles") or []
    norm = []
    for it in detalles:
        if not isinstance(it, dict): continue
        sust = (it.get("sustancia") or "").strip()
        reac = it.get("reaccion") or None
        if sust: norm.append({"sustancia": sust, "reaccion": reac})
    if not tiene:
        heur2 = _heuristic_alergias_from_text(text)
        if heur2 and heur2["tiene_alergias"]:
            tiene = True
            norm = heur2["detalle"]
    return {"ficha": {"alergia_medicacion": {"alergias": {"tiene_alergias": tiene, "detalle": norm}}}}

# ---------- LLM: Medicación habitual (módulo 2 / fase meds) ----------
def _llm_extract_medicacion(text: str) -> Dict[str, Any]:
    if not (text or "").strip():
        return {}
    system = (
        "Sos un normalizador de medicación en *Argentina*. "
        "Devolvé SOLO JSON: {\"meds\":[{\"droga\": str, \"dosis\": str|null, \"frecuencia\": str|null}]}. "
        "Aceptá nombres comerciales (p.ej., Paxon=losartán), incluí puff/inhaladores, no inventes dosis/frecuencia."
    )
    user = f"Texto del paciente:\n{text}"
    raw = _call_openai([{"role":"system","content":system},{"role":"user","content":user}], max_tokens=320)
    try: obj = json.loads(raw) if raw else {}
    except Exception: obj = {}
    meds_in = obj.get("meds") or []
    meds_out = []
    for it in meds_in:
        if not isinstance(it, dict): continue
        d = (it.get("droga") or "").strip()
        if not d: continue
        meds_out.append({"droga": d, "dosis": (it.get("dosis") or None), "frecuencia": (it.get("frecuencia") or None)})
    return {"ficha": {"alergia_medicacion": {"medicacion_habitual": meds_out}}}

# ---------- LLM: Ilícitas (módulo 2 / fase illicit) ----------
def _llm_extract_ilicitas(text: str) -> Dict[str, Any]:
    if not (text or "").strip():
        return {}
    system = (
        "Extraé consumo de *sustancias ilícitas*. Devolvé SOLO JSON:\n"
        '{"consume": bool, "items": [{"sustancia": str, "frecuencia": str|null, "ultimo_consumo": str|null}]}\n'
        "Si el paciente niega (“no consumo drogas/porro/etc.”), poné consume=false e items=[]. "
        "No juzgues ni expandas."
    )
    user = f"Texto del paciente:\n{text}"
    raw = _call_openai([{"role":"system","content":system},{"role":"user","content":user}], max_tokens=300)
    try: obj = json.loads(raw) if raw else {}
    except Exception: obj = {}
    consume = bool(obj.get("consume", False))
    items = []
    for it in obj.get("items") or []:
        if not isinstance(it, dict): continue
        sust = (it.get("sustancia") or "").strip()
        if not sust: continue
        items.append({"sustancia": sust, "frecuencia": (it.get("frecuencia") or None), "ultimo_consumo": (it.get("ultimo_consumo") or None)})
    # post: si LLM dijo false pero hay keywords claras, forzar true
    if not consume:
        loc = _parse_ilicitas(text)
        if loc:
            d = loc["ficha"]["sustancias"]["ilicitas"]
            consume = d.get("consume", False)
            items = d.get("detalle", [])
    return {"ficha": {"sustancias": {"ilicitas": {"consume": consume, "detalle": items}}}}

# Router-friendly: LLM parse por módulo/fase
def llm_parse_modular(text: str, module_idx: int, state: Any = None) -> Dict[str, Any]:
    if module_idx == 0:
        # SNOMED + fallback con comillas (ya implementado abajo en versión extensa en tu código anterior).
        # Para ahorrar tokens, reuso extracción anterior y, si no hay mapeo confiable, dejo el motivo original.
        base = _llm_extract_generales_full(text or "")
        # Fallback “entre comillas” para motivo si no vino normalizado:
        try:
            cob = (((base or {}).get("ficha") or {}).get("cobertura") or {})
            if not cob.get("motivo_cirugia"):
                m = re.search(r"(?i)^motivo.*?:\s*(.+)$", text or "")
                cand = (m.group(1).strip() if m else None)
                if cand:
                    base = _deep_merge_dict(base, {"ficha": {"cobertura": {"motivo_cirugia": f"\"{cand}\""}}})
        except Exception:
            pass
        return base or {}

    if module_idx == 1:
        return _llm_extract_alergias(text or "")

    if module_idx == 2:
        phase = getattr(state, "_mod2_phase", "meds") if state is not None else "meds"
        if phase == "illicit":
            return _llm_extract_ilicitas(text or "")
        return _llm_extract_medicacion(text or "")

    return {}

# ================== Confirmación ==================
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
        nombre = datos.get("nombre_completo"); fnac = datos.get("fecha_nacimiento"); edad = datos.get("edad")
        peso = antropo.get("peso_kg"); talla = antropo.get("talla_cm"); imc = antropo.get("imc")
        os_ = cob.get("obra_social"); afil = cob.get("afiliado"); motivo = cob.get("motivo_cirugia")
        lines = []
        if any([nombre, dni, fnac, edad, peso, talla, imc, os_, afil, motivo]): lines.append("✔️ Registré:")
        if _fmt(nombre) or _fmt(dni):
            left = _fmt(nombre) or ""; right = f"DNI {dni}" if _fmt(dni) else ""
            lines.append(f"• {left}{(' — ' + right) if left and right else right}")
        if _fmt(fnac) or _fmt(edad):
            left = _fmt(fnac) or ""; right = f"({_fmt(edad)} años)" if _fmt(edad) else ""
            lines.append(f"• Nac.: {left} {right}".strip())
        if _fmt(peso) or _fmt(talla) or _fmt(imc):
            parts = []
            if _fmt(peso): parts.append(f"Peso {peso} kg")
            if _fmt(talla): parts.append(f"Talla {talla} cm")
            if _fmt(imc): parts.append(f"IMC {imc}")
            lines.append("• " + ", ".join(parts))
        if _fmt(os_) or _fmt(afil):
            parts = []
            if _fmt(os_): parts.append(f"Obra social: {os_}")
            if _fmt(afil): parts.append(f"Afiliado: {afil}")
            lines.append("• " + " — ".join(parts))
        if _fmt(motivo): lines.append(f"• Motivo: {motivo}")
        return "\n".join([l for l in lines if l])

    if module_idx == 1:
        am = ficha.get("alergia_medicacion", {}) if isinstance(ficha.get("alergia_medicacion"), dict) else {}
        alg = am.get("alergias", {}) if isinstance(am.get("alergias"), dict) else {}
        tiene = alg.get("tiene_alergias"); detalles = alg.get("detalle") or []
        if tiene is False: return "✔️ Registré: sin alergias conocidas."
        if detalles:
            lines = ["✔️ Alergias:"]
            for d in detalles:
                if not isinstance(d, dict): continue
                sust = d.get("sustancia"); reac = d.get("reaccion")
                if sust and reac: lines.append(f"• {sust}: {reac}")
                elif sust: lines.append(f"• {sust}")
            return "\n".join(lines)
        return ""

    if module_idx == 2:
        lines = []
        am = ficha.get("alergia_medicacion", {}) if isinstance(ficha.get("alergia_medicacion"), dict) else {}
        meds = am.get("medicacion_habitual") or []
        if meds:
            lines.append("✔️ Medicación habitual:")
            for m in meds:
                if not isinstance(m, dict): continue
                droga = m.get("droga"); dosis = m.get("dosis"); frec = m.get("frecuencia")
                if not droga: continue
                extra = " ".join(x for x in [dosis or "", f"({frec})" if frec else ""] if x).strip()
                lines.append(f"• {droga}" + (f" — {extra}" if extra else ""))
        il = (ficha.get("sustancias", {}) or {}).get("ilicitas", {})
        if isinstance(il, dict):
            consume = il.get("consume")
            det = il.get("detalle") or []
            if consume is False:
                lines.append("✔️ Sin consumo de sustancias ilícitas.")
            elif det:
                lines.append("✔️ Sustancias ilícitas:")
                for it in det:
                    if not isinstance(it, dict): continue
                    s = it.get("sustancia"); fr = it.get("frecuencia"); uc = it.get("ultimo_consumo")
                    extra = " ".join(x for x in [fr or "", uc or ""] if x).strip()
                    lines.append(f"• {s}" + (f" — {extra}" if extra else ""))
        return "\n".join(lines).strip()

    public_items = [(k, v) for k, v in (ficha.items()) if not str(k).startswith("_")]
    if not public_items: return ""
    modulo_name = MODULES[module_idx]["name"] if 0 <= module_idx < len(MODULES) else "Bloque"
    joined = "; ".join(f"{k}: {v}" for k, v in public_items)
    return f"Anoté en {modulo_name}: {joined}."
