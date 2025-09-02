# /app/services/validators.py
from __future__ import annotations

import re
from datetime import date, datetime
from typing import Optional, Tuple, Dict

# --- DNI ---

def parse_dni(text: str) -> Optional[str]:
    if not text:
        return None
    # acepta 7-8 dígitos, con o sin puntos
    m = re.search(r"(?<!\d)(\d{7,8})(?!\d)", re.sub(r"[.\s]", "", text))
    return m.group(1) if m else None

# --- Fechas / Edad ---

_DDMMYYYY = re.compile(r"(?<!\d)(0?[1-9]|[12]\d|3[01])[-/](0?[1-9]|1[0-2])[-/](\d{4})(?!\d)")

def parse_fecha(text: str) -> Optional[date]:
    if not text:
        return None
    m = _DDMMYYYY.search(text)
    if not m:
        return None
    d, mth, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
    try:
        return date(y, mth, d)
    except ValueError:
        return None

def edad_from_fecha_nacimiento(fnac: Optional[date]) -> Optional[int]:
    if not fnac:
        return None
    today = date.today()
    years = today.year - fnac.year - ((today.month, today.day) < (fnac.month, fnac.day))
    return max(0, years)

# --- Antropometría ---

def parse_peso_kg(text: str) -> Optional[float]:
    if not text:
        return None
    t = text.lower().replace(",", ".")
    # prioriza números seguidos de kg
    m = re.search(r"(\d+(?:\.\d+)?)\s*kg", t)
    if not m:
        # cualquier número razonable 25-300
        m = re.search(r"(?<!\d)(\d+(?:\.\d+)?)(?!\d)", t)
    if not m:
        return None
    try:
        val = float(m.group(1))
        if 25.0 <= val <= 300.0:
            return round(val, 2)
    except Exception:
        pass
    return None

def parse_talla_cm(text: str) -> Optional[int]:
    if not text:
        return None
    t = text.lower().replace(",", ".")
    # casos en cm
    m = re.search(r"(?<!\d)(\d{2,3})\s*cm(?![a-z])", t)
    if m:
        try:
            val = int(m.group(1))
            if 100 <= val <= 230:
                return val
        except Exception:
            pass
    # casos en metros (1.70, 1,70, 1m70)
    m = re.search(r"(?<!\d)(1(?:\.\d{1,2})?)(?:\s*m)?", t)
    if m:
        try:
            mts = float(m.group(1))
            cm = int(round(mts * 100))
            if 100 <= cm <= 230:
                return cm
        except Exception:
            pass
    # número suelto razonable
    m = re.search(r"(?<!\d)(\d{2,3})(?!\d)", t)
    if m:
        try:
            val = int(m.group(1))
            if 100 <= val <= 230:
                return val
        except Exception:
            pass
    return None

def calc_imc(peso_kg: Optional[float], talla_cm: Optional[int]) -> Optional[float]:
    try:
        if peso_kg is None or talla_cm is None:
            return None
        m = float(talla_cm) / 100.0
        if m <= 0:
            return None
        imc = float(peso_kg) / (m * m)
        return round(imc, 1)
    except Exception:
        return None

# --- Cobertura ---

def parse_afiliado(text: str) -> Optional[str]:
    if not text:
        return None
    m = re.search(r"([A-Z0-9]{4,})", text.replace(" ", "").upper())
    return m.group(1) if m else None

# --- Sustancias ---

def parse_tabaco(text: str) -> Tuple[Optional[bool], Optional[float], Optional[float]]:
    """
    Devuelve (consume, paquetes_dia, anios_paquete)
    """
    if not text:
        return None, None, None
    t = text.lower()
    # negaciones claras
    if re.search(r"\b(no\s*fuma|no fumador|nunca fum[oó])\b", t):
        return False, None, None
    consume = None
    if "fum" in t:
        consume = True
    # paquetes/día
    p = None
    m = re.search(r"(\d+(?:\.\d+)?)\s*(paquetes?/d[ií]a|pack/?d|pd)", t)
    if m:
        try:
            p = float(m.group(1))
        except Exception:
            pass
    # años-paquete
    ap = None
    m = re.search(r"(\d+(?:\.\d+)?)\s*(a[nñ]os?\s*paquete|ap)\b", t)
    if m:
        try:
            ap = float(m.group(1))
        except Exception:
            pass
    return consume, p, ap

def parse_alcohol(text: str) -> Tuple[Optional[bool], Optional[int]]:
    """
    Devuelve (consume, tragos_semana)
    """
    if not text:
        return None, None
    t = text.lower()
    if re.search(r"\b(no\s*bebe|no toma|abstemio)\b", t):
        return False, None
    consume = True if re.search(r"\b(bebe|toma|alcohol)\b", t) else None
    tragos = None
    m = re.search(r"(\d+)\s*(tragos?|u?nidades?)\s*(/|por)?\s*(sem|semana|sem)\b", t)
    if m:
        try:
            tragos = int(m.group(1))
        except Exception:
            pass
    return consume, tragos

# --- Vía aérea ---

def parse_via_aerea(text: str) -> Dict[str, Optional[bool]]:
    """
    Devuelve flags simples para vía aérea.
    """
    t = (text or "").lower()
    flags = {
        "intubacion_dificil": None,
        "protesis_dentaria": None,
        "dientes_flojos": None,
        "ronquidos_apnea": None,
    }
    if re.search(r"intubaci[oó]n\s+d[ií]ficil", t):
        flags["intubacion_dificil"] = True
    if re.search(r"pr[oó]tesis\s+dent", t):
        flags["protesis_dentaria"] = True
    if "diente flojo" in t or "piezas flojas" in t:
        flags["dientes_flojos"] = True
    if "apnea" in t or "ronca" in t:
        flags["ronquidos_apnea"] = True
    # negaciones básicas
    if re.search(r"sin\s+(pr[oó]tesis|apnea|dientes? flojos)", t):
        if "prótesis" in t or "protesis" in t:
            flags["protesis_dentaria"] = False
        if "apnea" in t:
            flags["ronquidos_apnea"] = False
        if "dientes flojos" in t o r "diente flojo" in t:
            flags["dientes_flojos"] = False
    return flags

# --- Rangos de laboratorio ---

def hb_en_rango(hb: Optional[float]) -> bool:
    try:
        v = float(hb)
        return 5.0 <= v <= 25.0
    except Exception:
        return False

def plaquetas_en_rango(plt: Optional[int]) -> bool:
    try:
        v = int(plt)
        return 20000 <= v <= 1500000
    except Exception:
        return False

def creatinina_en_rango(crea: Optional[float]) -> bool:
    try:
        v = float(crea)
        return 0.1 <= v <= 15.0
    except Exception:
        return False

def inr_en_rango(inr: Optional[float]) -> bool:
    try:
        v = float(inr)
        return 0.5 <= v <= 10.0
    except Exception:
        return False


# === NUEVO: Validadores usados por api.health ===

# Mapeo mínimo de códigos de país -> ISO2 (extensible)
_CC_TO_ISO2 = {
    "54": "AR",  # Argentina
    "56": "CL",  # Chile
    "57": "CO",  # Colombia
    "52": "MX",  # México
    "34": "ES",  # España
}

def _extraer_cod_pais(phone: str) -> str:
    """
    Extrae el código de país del número (e.g. '+54911...' -> '54').
    Si no puede, devuelve ''.
    """
    if not phone:
        return ""
    s = re.sub(r"[^\d]", "", phone)  # solo dígitos
    # Heurística: los móviles internacionales empiezan por el código de país (2–3 dígitos)
    return s[:2] if len(s) >= 2 else ""

def validate_phone_country(phone: str, wa_client) -> Dict[str, str | bool]:
    """
    Valida que el número pertenezca a un país permitido.
    Devuelve: {"valid": bool, "country": str}
    - Implementación laxa por ahora: marca válido y mapea el país si puede.
    """
    cc = _extraer_cod_pais(phone)
    iso2 = _CC_TO_ISO2.get(cc, "unknown")
    # Si querés restringir países, cambiá la condición de valid.
    valid = True  # por ahora no bloquea
    return {"valid": valid, "country": iso2}

def validate_message_content(message: str, sender_phone: str, wa_client) -> Dict[str, bool]:
    """
    Valida el contenido básico del mensaje.
    Devuelve: {"valid": bool}
    Reglas mínimas:
      - no vacío
      - al menos 2 caracteres útiles
      - evita solo emojis/espacios
    """
    if not message:
        return {"valid": False}
    txt = message.strip()
    if len(txt) < 2:
        return {"valid": False}
    # Si querés agregar listas de palabras prohibidas, hacelo acá.
    return {"valid": True}
