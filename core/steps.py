from __future__ import annotations

from typing import Any, Dict, Optional, Tuple
import re
from datetime import datetime, date

# ============================================================================
# Definición de MÓDULOS (en orden)
#   >> Módulo 0 unifica: DNI + Datos personales + Antropometría + Cobertura/Motivo
#      con prompt "regex-friendly" para WhatsApp. El resto de módulos siguen igual.
# ============================================================================
MODULES = [
    {
        "name": "Datos generales",
        "use_llm": True,  # LLM puede usarse en rutas para normalizar motivo
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
# Helpers
# ============================================================================

def _ensure_ficha(state: Any) -> None:
    """Garantiza que state.ficha exista."""
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
    Ignora claves internas (empiezan con "_").
    """
    _ensure_ficha(state)
    data = patch.get("ficha", patch)
    if not isinstance(data, dict):
        return state

    if isinstance(state.ficha, dict):
        for k, v in data.items():
            if isinstance(k, str) and k.startswith("_"):
                continue
            state.ficha[k] = v
        return state

    for k, v in data.items():
        if isinstance(k, str) and k.startswith("_"):
            continue
        if hasattr(state.ficha, k):
            setattr(state.ficha, k, v)
    return state


def prompt_for_module(idx: int) -> str:
    if 0 <= idx < len(MODULES):
        return MODULES[idx]["prompt"]
    return "Continuemos con el siguiente bloque."


def advance_module(state: Any) -> Tuple[Optional[int], Optional[str]]:
    """Devuelve el índice del módulo a preguntar ahora y su prompt."""
    idx = getattr(state, "module_idx", 0) or 0
    if idx < 0:
        idx = 0
    if idx >= len(MODULES):
        return None, None
    return idx, prompt_for_module(idx)

# ============================================================================
# Regex y parsers específicos por módulo
# ============================================================================

# Bloque guiado etiquetas (Módulo 0)
_RE_FLAGS = re.IGNORECASE | re.MULTILINE

_RE_NOMBRE = re.compile(
    r"^nombre y apellido:\s*([A-Za-zÁÉÍÓÚÜÑñ'´`\- ]{3,}(?:\s+[A-Za-zÁÉÍÓÚÜÑñ'´`\- ]{2,})+)\s*$",
    _RE_FLAGS,
)
_RE_DNI_LABELED = re.compile(r"^dni.*?:\s*([0-9][0-9.\s]{5,})$", _RE_FLAGS)
_RE_FNAC = re.compile(r"^fecha nacimiento.*?:\s*(\d{1,2}/\d{1,2}/\d{4})$", _RE_FLAGS)
# Acepta 170, 1.70 o 1,70; el "cm" no es obligatorio
_RE_PESO = re.compile(r"^peso.*?kg.*?:\s*([0-9]{1,3}(?:[.,][0-9]{1,2})?)$", _RE_FLAGS)
_RE_TALLA = re.compile(r"^talla.*?:\s*([0-9]{1,3}(?:[.,][0-9]{1,2})?)$", _RE_FLAGS)
_RE_OS = re.compile(r"^obra social:\s*([A-Za-zÁÉÍÓÚÜÑñ0-9 .,'\-]{2,60})$", _RE_FLAGS)
_RE_AFIL = re.compile(r"^(?:n°|nº|num(?:ero)?)[\s_-]*afiliad[oa]:\s*([A-Za-z0-9\-./]{3,30})$", _RE_FLAGS)
_RE_MOTIVO = re.compile(r"^motivo.*?:\s*(.{3,200})$", _RE_FLAGS)
# Si algún día lo querés volver a pedir, ya queda el regex
_RE_FECHA_EVAL = re.compile(r"^fecha.*evaluaci[oó]n.*?:\s*(\d{1,2}/\d{1,2}/\d{4})$", _RE_FLAGS)

# Fallbacks (libre)
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
    """
    Nombre propio con capitalización correcta: 'perez hernan' -> 'Perez Hernan';
    preserva guiones y apóstrofes; minúsculas para partículas (de, del, la, los, y, da, das, di, van, von) salvo si es la primera palabra.
    """
    if not s:
        return s
    particles = {"de", "del", "la", "las", "los", "y", "da", "das", "di", "van", "von"}
    tokens = [t for t in re.split(r"\s+", s.strip()) if t]
    out: list[str] = []

    def cap(word: str) -> str:
        # maneja guiones y apóstrofes
        def cap_simple(w: str) -> str:
            return w[:1].upper() + w[1:].lower() if w else w
        w = "'".join(cap_simple(p) for p in word.split("'"))
        parts = w.split("-")
        return "-".join(cap_simple(p) for p in parts)

    for i, t in enumerate(tokens):
        low = t.lower()
        if i > 0 and low in particles:
            out.append(low)
        else:
            out.append(cap(t))
    return " ".join(out)


def _norm_year(y: int) -> int:
    if y < 100:
        century = 2000 if y <= 21 else 1900
        return century + y
    return y


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


def normalize_motivo_clinico(context_text: str, raw: Optional[str]) -> Optional[str]:
    """Heurística mínima (dejamos el LLM para rutas)."""
    if not raw:
        return None
    s = raw.lower().strip()
    reps = [
        (r"apend", "apendicectomía"),
        (r"ves[ií]cul|colecist", "colecistectomía"),
        (r"hernia inguinal", "hernioplastia inguinal"),
        (r"catarat", "facoemulsificación de catarata"),
    ]
    for k, v in reps:
        if re.search(k, s):
            return v
    return raw.strip().capitalize()

# ---------------- MÓDULO 0: DATOS GENERALES ----------------

def _parse_generales(text: str) -> Dict[str, Any]:
    text = text or ""

    # Saludo simple para no fallar en el primer input
    if _GREETING_RE.search(text.strip()):
        return {"_start": True}

    # 1) Intento bloque etiquetado (alta precisión)
    nombre = (_RE_NOMBRE.search(text) or [None, None])[1]
    dni_raw = (_RE_DNI_LABELED.search(text) or [None, None])[1]
    fnac = (_RE_FNAC.search(text) or [None, None])[1]
    peso_s = (_RE_PESO.search(text) or [None, None])[1]
    talla_s = (_RE_TALLA.search(text) or [None, None])[1]
    os_ = (_RE_OS.search(text) or [None, None])[1]
    afiliado = (_RE_AFIL.search(text) or [None, None])[1]
    motivo = (_RE_MOTIVO.search(text) or [None, None])[1]
    feval = (_RE_FECHA_EVAL.search(text) or [None, None])[1]

    # 2) Fallback libre (si faltan campos)
    if not nombre:
        m = _NAME_FREE_RE.search(text)
        if m:
            nombre = " ".join(m.group("nombre").split())
    if not dni_raw:
        m = _DNI_FREE_RE.search(text)
        if m:
            dni_raw = m.group("dni")
    if not fnac:
        m = _DOB_FREE_RE.search(text)
        if m:
            d = int(m.group("d")); mth = int(m.group("m")); y = _norm_year(int(m.group("y")))
            fnac = f"{d:02d}/{mth:02d}/{y:04d}"
    if not peso_s:
        m = _WEIGHT_FREE_RE.search(text)
        if m:
            peso_s = m.group("peso")
    if not talla_s:
        # captura libre (cm o m)
        m = _HEIGHT_FREE_CM_RE.search(text)
        if m:
            talla_s = m.group("talla")
        else:
            m2 = _HEIGHT_FREE_M_RE.search(text)
            if m2:
                try:
                    metros = float(m2.group("metros").replace(",", "."))
                    talla_s = str(metros)  # lo normalizamos más abajo
                except Exception:
                    pass
    if not os_:
        m = _OS_FREE_RE.search(text)
        if m:
            os_ = m.group("os").strip()
    if not afiliado:
        m = _AFIL_FREE_RE.search(text)
        if m:
            afiliado = m.group("afil").strip()
    if not motivo:
        m = _MOTIVO_FREE_RE.search(text)
        if m:
            motivo = m.group("motivo").strip()

    # 3) Normalizaciones y validaciones
    out_dni: Optional[str] = None
    if dni_raw:
        cleaned = re.sub(r"[.\s]", "", dni_raw)
        if cleaned.isdigit():
            cleaned = cleaned.lstrip("0") or "0"
            if 6 <= len(cleaned) <= 10:
                out_dni = cleaned
    fnac_std = _parse_date_ddmmyyyy(fnac) if fnac else None

    peso: Optional[float] = None
    if peso_s:
        try:
            peso = float(peso_s.replace(",", "."))
            if not (20 <= peso <= 300):
                peso = None
        except Exception:
            peso = None

    talla: Optional[int] = None
    if talla_s:
        ss = talla_s.strip().replace(",", ".")
        try:
            if "." in ss:
                # asume metros si 0.9–2.5
                val = float(ss)
                if 0.9 <= val <= 2.5:
                    t = int(round(val * 100))
                else:
                    t = int(round(val))  # fallback raro
            else:
                t = int(ss)
                if t <= 3:  # 1–3 -> metros
                    t = int(round(float(ss) * 100))
            if 100 <= t <= 230:
                talla = t
        except Exception:
            talla = None

    os_val = (os_ or "").strip(" -:") or None
    afiliado_val = (afiliado or "").strip() or None
    motivo_val = (motivo or "").strip()
    if motivo_val:
        motivo_val = motivo_val[:200]
    else:
        motivo_val = None

    feval_std = _parse_date_ddmmyyyy(feval) if feval else None
    if not feval_std:
        today = date.today()
        feval_std = f"{today.day:02d}/{today.month:02d}/{today.year:04d}"

    edad = _calc_edad(fnac_std)
    imc = _calc_imc(peso, talla)

    # 4) Construcción del patch anidado según schemas
    ficha: Dict[str, Any] = {}

    if out_dni:
        ficha["dni"] = out_dni

    datos: Dict[str, Any] = {}
    if nombre:
        datos["nombre_completo"] = _smart_name_capitalize(nombre)
    if fnac_std:
        datos["fecha_nacimiento"] = fnac_std
    if edad is not None:
        datos["edad"] = edad
    if feval_std:
        # registrar pero no mostrar en la confirmación (lo ocultamos allí)
        datos["fecha_evaluacion"] = feval_std
    if datos:
        ficha["datos"] = datos

    antropo: Dict[str, Any] = {}
    if peso is not None:
        antropo["peso_kg"] = peso
    if talla is not None:
        antropo["talla_cm"] = talla
    if imc is not None:
        antropo["imc"] = imc
    if antropo:
        ficha["antropometria"] = antropo

    # Normalizar motivo clínico (heurística mínima aquí; LLM en rutas puede sobreescribir)
    motivo_norm = normalize_motivo_clinico(text, motivo_val) if motivo_val else None

    cobertura: Dict[str, Any] = {}
    if os_val:
        cobertura["obra_social"] = os_val
    if afiliado_val:
        cobertura["afiliado"] = afiliado_val
    if motivo_norm:
        cobertura["motivo_cirugia"] = motivo_norm
    if cobertura:
        ficha["cobertura"] = cobertura

    if not ficha:
        return {}

    return {"ficha": ficha}

# ---------------- RESTO DE PARSERS (módulos 1..5) ----------------
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
        out["alergia_medicacion"]["alergias"] = {"tiene_alergias": True, "detalle": [{"sustancia": ma.group("alergias").strip()}]}
    mm = _MEDIC_RE.search(text or "")
    if mm:
        out.setdefault("alergia_medicacion", {})
        out["alergia_medicacion"].setdefault("medicacion_habitual", [])
        out["alergia_medicacion"]["medicacion_habitual"].append({"droga": mm.group("medicacion").strip()})
    if not out:
        return {}
    return {"ficha": out}

def _parse_antecedentes(text: str) -> Dict[str, Any]:
    m = _ANTEC_RE.search(text or "")
    if not m:
        return {}
    return {"ficha": {"antecedentes": {"otros": [m.group("antecedentes").strip()]}}}

def _parse_complementarios(text: str) -> Dict[str, Any]:
    m = _COMPL_RE.search(text or "")
    if not m:
        return {}
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
    if not out:
        return {}
    return {"ficha": out}

def _parse_via_aerea(text: str) -> Dict[str, Any]:
    m = _VA_RE.search(text or "")
    if not m:
        return {}
    return {"ficha": {"via_aerea": {"otros": [m.group("via_aerea").strip()]}}}

# Mapa índice -> parser
_PARSERS = {
    0: _parse_generales,
    1: _parse_alerg_med,
    2: _parse_antecedentes,
    3: _parse_complementarios,
    4: _parse_sustancias,
    5: _parse_via_aerea,
}

def fill_from_text_modular(state: Any, module_idx: int, text: str) -> Dict[str, Any]:
    """Parser local por módulo (reglas simples)."""
    parser = _PARSERS.get(module_idx)
    if not parser:
        return {}
    data = parser(text or "")
    if not data:
        return {}
    return data

def llm_parse_modular(text: str, module_idx: int) -> Dict[str, Any]:
    """Stub: el LLM se usa desde rutas para normalizar 'motivo_cirugia' si está disponible."""
    return {}

def _fmt(v: Any) -> str:
    return "-" if v in (None, "", []) else str(v)

def summarize_patch_for_confirmation(patch: Dict[str, Any], module_idx: int) -> str:
    """
    Resume lo capturado para confirmación. Evita mostrar flags internos.
    Si detecta solo _start en el módulo 0, devuelve un saludo básico (rutas lo sobreescriben).
    """
    ficha = patch.get("ficha", patch) or {}
    if not isinstance(ficha, dict):
        return "No pude extraer datos de este bloque."

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
        # NOTA: ocultamos fecha_evaluacion en la confirmación
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
        return "No pude extraer datos de este bloque."
    modulo_name = MODULES[module_idx]["name"] if 0 <= module_idx < len(MODULES) else "Bloque"
    joined = "; ".join(f"{k}: {v}" for k, v in public_items)
    return f"Anoté en {modulo_name}: {joined}."
