# /app/core/settings.py
from __future__ import annotations
import os
from pathlib import Path

# ---------- paths base ----------
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.getenv("DATA_DIR", BASE_DIR / "data"))
DATA_DIR.mkdir(parents=True, exist_ok=True)

# ---------- artefactos de conversación ----------
CONVERSATION_HISTORY_DIR = Path(
    os.getenv("CONVERSATION_HISTORY_DIR", DATA_DIR / "conversations")
)
CONVERSATION_HISTORY_DIR.mkdir(parents=True, exist_ok=True)

TAKEOVER_FILE = Path(os.getenv("TAKEOVER_FILE", DATA_DIR / "takeover.flag"))

# ---------- otros opcionales ----------
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")  # si lo usas
ENV = os.getenv("ENV", "production")

# ---------- objeto settings (compatibilidad) ----------
class _Settings:
    # Paths
    BASE_DIR: Path = BASE_DIR
    DATA_DIR: Path = DATA_DIR
    CONVERSATION_HISTORY_DIR: Path = CONVERSATION_HISTORY_DIR
    TAKEOVER_FILE: Path = TAKEOVER_FILE
    # Otros
    OPENAI_API_KEY: str | None = OPENAI_API_KEY
    ENV: str = ENV

settings = _Settings()

__all__ = [
    "BASE_DIR",
    "DATA_DIR",
    "CONVERSATION_HISTORY_DIR",
    "TAKEOVER_FILE",
    "OPENAI_API_KEY",
    "ENV",
    "settings",
]
