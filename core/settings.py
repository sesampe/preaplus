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
HEYOO_TOKEN = os.getenv("HEYOO_TOKEN", "")    # 👈 agregado para audio_processing
ENV = os.getenv("ENV", "production")

# ---------- Google Drive / Productos ----------
SERVICE_ACCOUNT_FILE = os.getenv("SERVICE_ACCOUNT_FILE", str(DATA_DIR / "gcp-sa.json"))
PRODUCT_LIST_FILE_ID = os.getenv("PRODUCT_LIST_FILE_ID", "")  # <-- pon aquí el fileId real de tu sheet
CATALOG_PDF_LINK = os.getenv("CATALOG_PDF_LINK", "")          # opcional
PRODUCTS_CACHE_FILE = str(DATA_DIR / "products_cache.json")

# ---------- objeto settings (compatibilidad) ----------
class _Settings:
    # Paths
    BASE_DIR: Path = BASE_DIR
    DATA_DIR: Path = DATA_DIR
    CONVERSATION_HISTORY_DIR: Path = CONVERSATION_HISTORY_DIR
    TAKEOVER_FILE: Path = TAKEOVER_FILE
    # Otros
    OPENAI_API_KEY: str | None = OPENAI_API_KEY
    HEYOO_TOKEN: str = HEYOO_TOKEN
    ENV: str = ENV
    # Drive/Productos
    SERVICE_ACCOUNT_FILE: str = SERVICE_ACCOUNT_FILE
    PRODUCT_LIST_FILE_ID: str = PRODUCT_LIST_FILE_ID
    CATALOG_PDF_LINK: str = CATALOG_PDF_LINK
    PRODUCTS_CACHE_FILE: str = PRODUCTS_CACHE_FILE

settings = _Settings()

__all__ = [
    "BASE_DIR",
    "DATA_DIR",
    "CONVERSATION_HISTORY_DIR",
    "TAKEOVER_FILE",
    "OPENAI_API_KEY",
    "HEYOO_TOKEN",          # 👈 agregado
    "ENV",
    "settings",
    "SERVICE_ACCOUNT_FILE",
    "PRODUCT_LIST_FILE_ID",
    "CATALOG_PDF_LINK",
    "PRODUCTS_CACHE_FILE",
]
