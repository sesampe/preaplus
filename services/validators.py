# validators.py
import re
from datetime import date, datetime
from typing import Optional, Tuple

# ===== Util =====

def _to_float(num: str) -> Optional[float]:
    if not num:
        return None
    num = num.strip().replace(",", ".")
    try:
        return float(num)
    except ValueError:
        return None

def _clamp(v: Optional[float], lo: float, hi: float) -> Optional[float]:
    if v is None:
        return None
    if v < lo or v > hi:
        return None
    return v

# ===== DNI =====

_DNI_RE = re.compile(r"\b(\d{7,9})\b")

def parse_dni(text: str) -> Optional[str]:
    # acepta con puntos también
    text_clean = re.sub(r"[.\s]", "", text or "")
    m = re.search(r"\b\d{7,9}\b", text_clean)
    return m.group(0) if m else None

# ===== Fechas =====

_DATE_RE = re.compile(r"\b(\d{1,2})[/-](\d{1,2})[/-](\d{2,4})\b")

def parse_fecha(text: str) -> Optional[date]:
    if not text:
        return None
    m = _DATE_RE.search(text)
    if not m:
        return None
    d, mth, y = m.groups()
    y = int(y)
    if y < 100:
        y += 1900 if y > 30 else 2000
    try:
        return date(int(y), int(mth), int(d))
    except ValueError:
        return None

def edad_from_fecha_nacimiento(fnac: Optional[date]) -> Optional[int]:
    if not fnac:
        return None
    today = date.today()
    years = today.year - fnac.year - ((today.month, today.day) < (fnac.month, fnac.day))
    return _clamp(years, 0, 120)

# ===== Antropometría =====

def parse_peso_kg(text: str) -> Optional[float]:
    if not text:
        return None
    m = re.search(r"(\d+[.,]?\d*)\s*(kg|kil|kilos|kilogramos)?\b", text, flags=re.I)
    val = _to_float(m.group(1)) if m else None
    return _clamp(val, 25.0, 300.0)

def parse_talla_cm(text: str) -> Optional[float]:
    if not text:
        return None
    # acepta "1.72 m", "172", "172cm", "1,72"
    m_m = re.search(r"(\d+[.,]?\d*)\s*m\b", text, flags=re.I)
    if m_m:
        meters = _to_float(m_m.group(1))
        if meters is not None:
            return _clamp(meters * 100.0, 100.0, 230.0)
    m_cm = re.search(r"\b(\d{2,3})(?:\s*cm)?\b", text, flags=re.I)
    if m_cm:
        cm = _to_float(m_cm.group(1))
        return _clamp(cm, 100.0, 230.0)
    return None

def calc_imc(peso_kg: Optional[float], talla_cm: Optional[float]) -> Optional[float]:
    if peso_kg is None or talla_cm is None:
        return None
    m = talla_cm / 100.0
    if m <= 0:
        return None
    imc = peso_kg / (m * m)
    return _clamp(round(imc, 1), 10.0, 80.0)

# ===== Cobertura =====

def parse_afiliado(text: str) -> Optional[str]:
    if not text:
        return None
    m = re.search(r"\b([A-Z0-9]{4,})\b", text, flags=re.I)
    return m.group(1) if m else None

# ===== Sustancias =====

def parse_tabaco(text: str) -> Tuple[Optional[bool], Optional[float], Optional[float]]:
    if not text:
        return None, None, None
    t = text.lower()
    if any(k in t for k in ["no fuma", "no fum", "niega tabaco"]):
        return False, None, None
    if any(k in t for k in ["fuma", "tabaco", "cigarr"]):
        # paquetes/día
        m = re.search(r"(\d+[.,]?\d*)\s*(pack|paquete|paq).{0,12}(dia|día)", t)
        paquetes = _to_float(m.group(1)) if m else None
        # años-paquete (si aparece)
        m2 = re.search(r"(\d+[.,]?\d*)\s*(años|anos).{0,8}(paq)", t)
        ap = _to_float(m2.group(1)) if m2 else None
        return True, paquetes, ap
    return None, None, None

def parse_alcohol(text: str) -> Tuple[Optional[bool], Optional[float]]:
    if not text:
        return None, None
    t = text.lower()
    if any(k in t for k in ["no bebe", "no toma", "niega alcohol"]):
        return False, None
    if any(k in t for k in ["bebe", "toma", "alcohol"]):
        m = re.search(r"(\d+[.,]?\d*)\s*(tragos|unidades|bebidas).{0,12}(semana)", t)
        ts = _to_float(m.group(1)) if m else None
        return True, ts
    return None, None

def parse_via_aerea(text: str):
    t = (text or "").lower()
    return {
        "intubacion_dificil": True if "intub" in t and "dific" in t else (False if "sin dificultad" in t else None),
        "piezas_flojas": True if any(k in t for k in ["diente flojo", "pieza floja"]) else (False if "sin piezas flojas" in t else None),
        "protesis": True if "prótesis" in t or "protesis" in t else (False if "sin prótesis" in t else None),
    }

# ===== Complementarios: rangos muy básicos =====

def hb_en_rango(x: Optional[float]) -> bool:
    return x is None or (2.0 <= x <= 22.0)

def plaquetas_en_rango(x: Optional[int]) -> bool:
    return x is None or (5_000 <= x <= 1_200_000)

def creatinina_en_rango(x: Optional[float]) -> bool:
    return x is None or (0.2 <= x <= 15.0)

def inr_en_rango(x: Optional[float]) -> bool:
    return x is None or (0.5 <= x <= 8.0)
