# core/validators.py
from __future__ import annotations

import re
from typing import Optional

from heyoo import WhatsApp

from core.logger import LoggerManager
from core.settings import settings


log = LoggerManager(name="validators", level="INFO", log_to_file=False).get_logger()

MIN_MESSAGE_LENGTH = 2
MAX_MESSAGE_LENGTH = 200
ALLOWED_COUNTRY_PREFIX = "54"


def validate_message_content(user_message: str, sender_phone: str, wa_client: WhatsApp) -> dict:
    if not user_message or len(user_message.strip()) == 0:
        log.warning(f"⚠️ Mensaje vacío de {sender_phone}")
        wa_client.send_message("No entendí tu mensaje, ¿podrías escribirlo de nuevo? ✍️", sender_phone)
        return {"valid": False, "status": "empty_message"}

    if len(user_message) > MAX_MESSAGE_LENGTH:
        log.warning(f"⚠️ Mensaje demasiado largo de {sender_phone}: {len(user_message)} chars")
        wa_client.send_message("Tu mensaje es muy largo. ¿Podrías resumirlo un poco? ✂️", sender_phone)
        return {"valid": False, "status": "long_message"}

    return {"valid": True, "status": "ok"}


def validate_phone_country(sender_phone: str, wa_client: WhatsApp) -> dict:
    if not sender_phone.startswith(ALLOWED_COUNTRY_PREFIX):
        log.warning(f"❌ País no permitido: {sender_phone}")
        wa_client.send_message("Este servicio solo está disponible para teléfonos de Argentina 🇦🇷", sender_phone)
        return {"valid": False, "status": "unsupported_country"}
    return {"valid": True, "status": "ok"}


def detect_prompt_injection(user_message: str) -> bool:
    peligros = [
        "olvida todas las instrucciones",
        "ignore previous instructions",
        "you are free now",
        "please jailbreak",
        "override all previous directions",
        "haz caso omiso de lo anterior",
        "desobedece las órdenes",
        "imagine you are playing",
    ]
    t = user_message.lower()
    return any(p in t for p in peligros)


# ---------------- Específicos clínicos ----------------

def is_valid_fecha_ddmmyyyy(fecha: str) -> bool:
    m = re.match(r"^(0[1-9]|[12]\d|3[01])/(0[1-9]|1[0-2])/(\d{4})$", fecha)
    return bool(m)


def parse_float_relaxed(s: str) -> Optional[float]:
    try:
        return float(s.replace(",", "."))
    except Exception:
        return None


def parse_int_relaxed(s: str) -> Optional[int]:
    try:
        return int(re.sub(r"[^\d]", "", s))
    except Exception:
        return None


def validar_peso_kg(peso: float) -> bool:
    try:
        return 25.0 <= float(peso) <= 300.0
    except Exception:
        return False


def validar_talla_cm(talla: int) -> bool:
    try:
        return 100 <= int(talla) <= 230
    except Exception:
        return False


def clamp_float(v: float, lo: float, hi: float) -> float:
    try:
        f = float(v)
        return max(lo, min(hi, f))
    except Exception:
        return v
