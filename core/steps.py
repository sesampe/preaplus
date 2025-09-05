from __future__ import annotations

from typing import Any, Dict, Optional, Tuple
import re
import os
from datetime import date

# ============================================================================
# Definición de MÓDULOS
# ============================================================================
MODULES = [
    {
        "name": "Datos generales",
        "use_llm": True,  # usar LLM para normalizar 'motivo_cirugia'
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

def merge_state(state: Any, patch: Dict[str, Any]) -> Any:
    """
    Deep-merge del patch en state.ficha (soporta dict o modelos Pydantic).
    Ignora claves internas (empiezan con '_').
    """
    _ensure_ficha(state)
    inc = patch.get("ficha", patch)
    if not isinstance(inc, dict):
        return state

    current = _to_dict(state.ficha)
    # elimina claves internas del patch
    inc = {k: v for k, v in inc.items() if not (isinstance(k, str) and k.startswith("_"))}
    merged = _deep_merge_dict(current, inc)

    if isinstance(state.ficha, dict):
        state.ficha.clear()
        state.ficha.update(merged)
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
# Talla: permite 170, 1.70 o 1,70 (sin exigir 'cm' textual)
_RE_TALLA = re.compile(r"^talla.*?:\s*([0-9]{1,3}(?:[.,][0-9]{1,2})?)$", _RE_FLAGS)
_RE_OS = re.compile(r"^obra social:\s*([A-Za-zÁÉÍÓÚÜÑñ0-9 .,'\-]{2,60})$", _RE_FLAGS)
_RE_AFIL = re.compile(r"^(?:n°|nº|num(?:ero)?)[\s_-]*afiliad[oa]:\s*([A-Za-z0-9\-./]{3,30})$", _RE_FLAGS)
_RE_MOTIVO = re.compile(r"^motivo.*?:\s*(.{3,200})$", _RE_FLAGS)

# Fallbacks libres
_GREETING_RE = re.compile(r"^\s*(hola|buenas|hey|hi|qué\s*tal|buen\s*d[ií]a|buenas\s*tardes|buenas\s*noches)\b", re.IGNORECASE)
_DNI_FREE_RE = re.compile(r"\b(?P<dni>\d{6,10})\b")
_NAME_FREE_RE = re.compile(r"(?:me\s+llamo|soy|nombre\s*:?\s*)(?P<nombre>[\wÀ-ÿ'´`\- ]{3,})", re.IGNORECASE)
_DOB_FREE_RE = re.compile(r"\b(?P<d>\d{1,2})[/-](?P<m>\d{1,2})[/-](?P<y>\d{2,4})\b")
_WEIGHT_FREE_RE = re.compile(r"(?:peso|pesa|kg)\D{0,5}(?P<peso>\d{1,3}(?:[.,]\d{1,2})?)", re.IGNORECASE)
_HEIGHT_FREE_CM_RE = re.compile(r"(?:mido|talla|altura|cm|mts?|metros?)\D{0,5}(?P<talla>\d{2,3})(?:[.,]\d+)?", re.IGNORECASE)
_HEIGHT_FREE_M_RE = re.compile(r"\b(?P<metros>1(?:[.,]\d{1,2})|0[.,]\d{1,2})\s*m\b", re.IGNORECASE)
_OS_FREE_RE = re.compile(r"(?:obra\s+social|prepaga|cobertura)\s*:?\s*[- ]*(?P<os>[A-Za-zÀ-ÿ0-9\. '\-]{2,})", re.IGNORECASE)
_AFIL_FREE_RE = re.compile(r"(?:nro?\.?\s*afiliad[oa]|afiliad[oa])\s*:?\s*[- ]*(?P<afil>[A-Za-z0-9\-\.\/]{3,})", re.IGNORECASE)
_MOTIVO_FREE_RE = re.compile(r"(?:motivo|cirug[ií]a|procedimiento)\s*:?\s*[- ]*(?P<motivo>[\wÀ-ÿ0-9,\. '\-]{3,})", re.IGNORECASE)

# ---------------- normalizadores/calculadores ----------------
def _smart_name_capitalize(s: str) -> str:
    """'perez hernan' -> 'Perez Hernan'; maneja partículas, guiones y apóstrofes."""
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
    text = text or ""

    # Si solo saluda, que routes.py mande el formulario
    if _GREETING_RE.search(text.strip()):
        return {"_start": True}

    # 1) Etiquetas
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
        if m: nombre = " ".join(m.group("nombre").split())
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

    # Registrar fecha de evaluación (hoy), no se muestra al paciente
    today = date.today()
    feval_std = f"{today.day:02d}/{today.month:02d}/{today.year:04d}"

    edad = _calc_edad(fnac_std)
    imc = _calc_imc(peso, talla)

    # 4) Patch anidado
    ficha: Dict[str, Any] = {}

    if out_dni: ficha["dni"] = out_dni

    datos: Dict[str, Any] = {}
    if nombre: datos["nombre_completo"] = _smart_name_capitalize(nombre)
    if fnac_std: datos["fecha_nacimiento"] = fnac_std
    if edad is not None: datos["edad"] = edad
    datos["fecha_evaluacion"] = feval_std  # siempre guardamos hoy
    if datos: ficha["datos"] = datos

    antropo: Dict[str, Any] = {}
    if peso is not None: antropo["peso_kg"] = peso
    if talla is not None: antropo["talla_cm"] = talla
    if imc is not None: antropo["imc"] = imc
    if antropo: ficha["antropometria"] = antropo

    # Motivo normalizado (heurística primero)
    motivo_norm = normalize_motivo_clinico_heuristic(motivo_val) if motivo_val else None

    cobertura: Dict[str, Any] = {}
    if os_val: cobertura["obra_social"] = os_val
    if afiliado_val: cobertura["afiliado"] = afiliado_val
    if motivo_norm: cobertura["motivo_cirugia"] = motivo_norm
    if cobertura: ficha["cobertura"] = cobertura

    return {"ficha": ficha} if ficha else {}

# ---------------- RESTO DE PARSERS (1..5) ----------------
_ALERG_RE = re.compile(r"(?:alergias?|al[ée]rgico[as]?)\s*:?\s*[- ]*(?P<alergias>.+)", re.IGNORECASE)
_MEDIC_RE = re.compile(r"(?:medicaci[oó]n|tomo|tomas|toma)\s*:?\s*[- ]*(?P<medicacion>.+)", re.IGNORECASE)
_ANTEC_RE = re.compile(r"(?:antecedentes?|enfermedades?|patolog[ií]a?s?)\s*:?\s*[- ]*(?P<antecedentes>.+)", re.IGNORECASE)
_COMPL_RE = re.compile(r"(?:estudios?|laboratorio|lab[s]?|electro|ecg|rx|placa|tc|mri|rmn)\s*:?\s*[- ]*(?P<complementarios>.+)", re.IGNORECASE)
_TABA_RE = re.compile(r"(?:tabaco|fumo|fum[oé]s?|cigarrillos?)\s*:?\s*[- ]*(?P<tabaco>.+)", re.IGNORECASE)
_ALCO_RE = re.compile(r"(?:alcohol|beb[eo]s?)\s*:?\s*[- ]*(?P<alcohol>.+)", re.IGNORECASE)
_OTRAS_RE = re.compile(r"(?:drogas?|sustancias?)\s*:?\s*[- ]*(?P<otras>.+)", re.IGNORECASE)
_VA_RE = re.compile(r"(?:v[ií]a\s*a[ée]rea|mallampati|apertura|bucal|dentari[ao]s?|piezas|pr[oó]tesis)\s*:?\s*[- ]*(?P<via_aerea>.+)", re.IGNORECASE)

def _parse_alerg_med(text: str) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    ma = _ALERG_RE.search(text or "")
    if ma:
        out.setdefault("alergia_medicacion", {})
        out["alergia_medicacion"]["alergias"] = {
            "tiene_alergias": True,
            "detalle": [{"sustancia": ma.group("alergias").strip()}]
        }
    mm = _MEDIC_RE.search(text or "")
    if mm:
        out.setdefault("alergia_medicacion", {})
        out["alergia_medicacion"].setdefault("medicacion_habitual", [])
        out["alergia_medicacion"]["medicacion_habitual"].append({"droga": mm.group("medicacion").strip()})
    return {"ficha": out} if out else {}

def _parse_antecedentes(text: str) -> Dict[str, Any]:
    m = _ANTEC_RE.search(text or "")
    if not m: return {}
    return {"ficha": {"antecedentes": {"otros": [m.group("antecedentes").strip()]}}}

def _parse_complementarios(text: str) -> Dict[str, Any]:
    m = _COMPL_RE.search(text or "")
    if not m: return {}
    return {"ficha": {"complementarios": {"imagenes": [{"estudio": m.group("complementarios").strip()}]}}}

def _parse_sustancias(text: str) -> Dict[str, Any]:
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
    m = _VA_RE.search(text or "")
    if not m: return {}
    return {"ficha": {"via_aerea": {"otros": [m.group("via_aerea").strip()]}}}

_PARSERS = {
    0: _parse_generales,
    1: _parse_alerg_med,
    2: _parse_antecedentes,
    3: _parse_complementarios,
    4: _parse_sustancias,
    5: _parse_via_aerea,
}

def fill_from_text_modular(state: Any, module_idx: int, text: str) -> Dict[str, Any]:
    parser = _PARSERS.get(module_idx)
    if not parser: return {}
    data = parser(text or "")
    return data or {}

# ============================================================================
# LLM: normalización SNOMED CT del motivo quirúrgico (Módulo 0)
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

def llm_parse_modular(text: str, module_idx: int) -> Dict[str, Any]:
    """Solo módulo 0: intenta mapear el motivo a término/procedimiento SNOMED CT."""
    if module_idx != 0:
        return {}

    # Detectar candidato rápidamente (si no vino con etiqueta)
    m = re.search(r"(?im)^motivo.*?:\s*(.+)$", text or "")
    candidate = (m.group(1).strip() if m else None) or ""
    if not candidate:
        m2 = re.search(
            r"(oper(ar|aci[oó]n)|sac(ar|an)|extirpar|quitar|me\s+hacen|intervenci[oó]n)[:\s,-]*([^\n]+)",
            text or "", re.IGNORECASE)
        if m2:
            candidate = (m2.group(4) or "").strip()

    if not candidate:
        return {}

    system = (
        "Eres un codificador clínico experto en procedimientos quirúrgicos. "
        "Tu tarea es estandarizar descripciones libres en español a un término de procedimiento "
        "según SNOMED CT (o el término clínico más equivalente si no hay correspondencia exacta). "
        "Responde SOLO en JSON válido con estas claves: "
        "{\"term_es\": string, \"sctid\": string|null, \"fsn_en\": string|null, \"confidence\": number}. "
        "No incluyas texto adicional."
    )

    user = (
        "Texto del paciente (español):\n"
        f"{text}\n\n"
        "Extrae y normaliza el procedimiento principal. Si dice 'hernia en ombligo', deberías devolver "
        "'hernioplastia umbilical'. Si dice 'me sacan la vesícula', 'colecistectomía'. "
        "Si no puedes decidir, devuelve sctid=null y confidence baja.\n\n"
        "Ejemplos de salida JSON:\n"
        "{\"term_es\":\"apendicectomía\",\"sctid\":\"80146002\",\"fsn_en\":\"Appendectomy (procedure)\",\"confidence\":0.95}\n"
        "{\"term_es\":\"facoemulsificación de catarata\",\"sctid\":\"428341000124107\",\"fsn_en\":\"Phacoemulsification of cataract (procedure)\",\"confidence\":0.92}\n"
        "{\"term_es\":\"hernioplastia umbilical\",\"sctid\":\"399125006\",\"fsn_en\":\"Repair of umbilical hernia (procedure)\",\"confidence\":0.9}\n\n"
        f"Motivo libre detectado: {candidate}"
    )

    raw = _call_openai(
        messages=[{"role": "system", "content": system},
                  {"role": "user", "content": user}],
        max_tokens=200,
    )
    if not raw:
        return {}

    # Intentar decodificar JSON simple
    import json
    term_es = None
    sctid = None
    fsn = None
    conf = 0.0
    try:
        obj = json.loads(raw)
        term_es = (obj.get("term_es") or "").strip() or None
        sctid = (obj.get("sctid") or None)
        fsn = (obj.get("fsn_en") or None)
        conf = float(obj.get("confidence") or 0)
    except Exception:
        # fallback: quizá devolvió solo texto; lo usamos como término
        term_es = raw.strip()

    if not term_es:
        return {}

    # Sanitizar término
    term_es = re.sub(r"[^A-Za-zÁÉÍÓÚÜÑáéíóúüñ\s\-]", "", term_es).strip()
    # Preferir término LLM si conf >= 0.7; si no, dejamos que la heurística local siga vigente
    patch: Dict[str, Any] = {"ficha": {"cobertura": {"motivo_cirugia": term_es}}} if conf >= 0.7 or sctid else {}
    # Adjuntar metadatos SNOMED si llegaron (no se muestran al paciente)
    if sctid or fsn:
        patch.setdefault("ficha", {}).setdefault("cobertura", {})["motivo_snomed"] = {
            "sctid": sctid, "fsn_en": fsn, "confidence": conf
        }
    return patch

# ============================================================================
# Confirmación
# ============================================================================
def _fmt(v: Any) -> str:
    return "-" if v in (None, "", []) else str(v)

def summarize_patch_for_confirmation(patch: Dict[str, Any], module_idx: int) -> str:
    ficha = patch.get("ficha", patch) or {}
    if not isinstance(ficha, dict):
        return "✔️ Registré los datos."

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
        # fecha_evaluacion se guarda pero NO se muestra
        peso = antropo.get("peso_kg")
        talla = antropo.get("talla_cm")
        imc = antropo.get("imc")
        os_ = cob.get("obra_social")
        afil = cob.get("afiliado")
        motivo = cob.get("motivo_cirugia")
        lineas = [
            "✔️ Registré:",
            f"• { _fmt(nombre) } — DNI { _fmt(dni) }",
            f"• Nac.: { _fmt(fnac) } ({ _fmt(edad) } años)",
            f"• Peso { _fmt(peso) } kg, Talla { _fmt(talla) } cm, IMC { _fmt(imc) }",
            f"• Obra social: { _fmt(os_) } — Afiliado: { _fmt(afil) }",
            f"• Motivo: { _fmt(motivo) }",
        ]
        return "\n".join(lineas)

    public_items = [(k, v) for k, v in ficha.items() if not str(k).startswith("_")]
    if not public_items:
        return "✔️ Registré los datos."
    modulo_name = MODULES[module_idx]["name"] if 0 <= module_idx < len(MODULES) else "Bloque"
    joined = "; ".join(f"{k}: {v}" for k, v in public_items)
    return f"Anoté en {modulo_name}: {joined}."
