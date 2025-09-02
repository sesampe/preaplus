# /app/core/settings.py
from __future__ import annotations
import os
from pathlib import Path

# Raíz del proyecto
BASE_DIR = Path(__file__).resolve().parent.parent

# Carpeta base de datos/archivos (puedes sobreescribir con env var)
DATA_DIR = Path(os.getenv("DATA_DIR", BASE_DIR / "data"))
DATA_DIR.mkdir(parents=True, exist_ok=True)

# Directorio donde se guarda el historial de conversaciones
CONVERSATION_HISTORY_DIR = Path(
    os.getenv("CONVERSATION_HISTORY_DIR", DATA_DIR / "conversations")
)
CONVERSATION_HISTORY_DIR.mkdir(parents=True, exist_ok=True)

# Archivo “flag” para takeover (si tu servicio lo usa)
TAKEOVER_FILE = Path(os.getenv("TAKEOVER_FILE", DATA_DIR / "takeover.flag"))

# (opcional) expórtalo explícitamente
__all__ = [
    "BASE_DIR",
    "DATA_DIR",
    "CONVERSATION_HISTORY_DIR",
    "TAKEOVER_FILE",
]
