# core/logger.py
import os
import sys
import logging
from logging.handlers import RotatingFileHandler

# Importá settings para loguear el system prompt
from core import settings

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
LOG_FILE = os.getenv("LOG_FILE", "logs/app.log")
LOG_FORMAT = "%(asctime)s | %(levelname)s | %(name)s | %(message)s"


def _build_handlers():
    handlers = []

    # Console
    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(LOG_LEVEL)
    ch.setFormatter(logging.Formatter(LOG_FORMAT))
    handlers.append(ch)

    # File (rotativo)
    if LOG_FILE:
        os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
        fh = RotatingFileHandler(
            LOG_FILE, maxBytes=2_000_000, backupCount=3, encoding="utf-8"
        )
        fh.setLevel(LOG_LEVEL)
        fh.setFormatter(logging.Formatter(LOG_FORMAT))
        handlers.append(fh)

    return handlers


def setup_logging():
    """
    Configura logging global y loguea temprano el estado del SYSTEM_PROMPT.
    Llamar esto APENAS arranca la app (antes de crear clientes LLM).
    """
    # force=True para reemplazar configuraciones previas (útil en entornos que ya tocan logging)
    logging.basicConfig(level=LOG_LEVEL, handlers=_build_handlers(), force=True)

    log = logging.getLogger("preanestesia")

    # --- Logueo temprano del SYSTEM_PROMPT ---
    try:
        sp_len = len(settings.SYSTEM_PROMPT or "")
        log.info(f"SYSTEM_PROMPT len={sp_len}")

        # Si usás archivo, mostrás la ruta (si está disponible en settings)
        sp_file = getattr(settings, "SYSTEM_PROMPT_FILE", None)
        if sp_file:
            log.info(f"SYSTEM_PROMPT_FILE={sp_file}")

        if sp_len == 0:
            log.warning(
                "SYSTEM_PROMPT vacío. Revisar SYSTEM_PROMPT_FILE / SYSTEM_PROMPT / encoding UTF-8."
            )
    except Exception as e:
        log.exception("No se pudo loguear SYSTEM_PROMPT: %s", e)

    return log


def get_logger(name: str = "preanestesia"):
    """
    Obtiene un logger con la configuración global asegurada.
    """
    root = logging.getLogger()
    if not root.handlers:
        # Si alguien importó este módulo sin llamar setup_logging(), garantizamos config mínima
        setup_logging()
    return logging.getLogger(name)
