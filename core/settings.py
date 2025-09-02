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
HEYOO_TOKEN = os.getenv("HEYOO_TOKEN", "")
ENV = os.getenv("ENV", "production")

# 🔐 Webhook / Meta
VERIFY_TOKEN = os.getenv("VERIFY_TOKEN", "")
APP_SECRET = os.getenv("APP_SECRET", "")  # App Secret de Meta/WhatsApp para firmar webhooks
HEYOO_PHONE_ID = os.getenv("HEYOO_PHONE_ID", "")
OWNER_PHONE_NUMBER = os.getenv("OWNER_PHONE_NUMBER", "")
SYSTEM_PROMPT_FILE = os.getenv("SYSTEM_PROMPT_FILE", str(DATA_DIR / "system_prompt.md"))

# ---------- Google Drive / Productos ----------
SERVICE_ACCOUNT_FILE = os.getenv("SERVICE_ACCOUNT_FILE", str(DATA_DIR / "gcp-sa.json"))
PRODUCT_LIST_FILE_ID = os.getenv("PRODUCT_LIST_FILE_ID", "")
CATALOG_PDF_LINK = os.getenv("CATALOG_PDF_LINK", "")
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

    # Webhook / Meta
    VERIFY_TOKEN: str = VERIFY_TOKEN
    APP_SECRET: str = APP_SECRET
    HEYOO_PHONE_ID: str = HEYOO_PHONE_ID
    OWNER_PHONE_NUMBER: str = OWNER_PHONE_NUMBER
    SYSTEM_PROMPT_FILE: str = SYSTEM_PROMPT_FILE

    # ---------- LLM ----------
    LLM_API_BASE: str = os.getenv("LLM_API_BASE", "https://api.openai.com/v1")
    LLM_HTTP_TIMEOUT: int = int(os.getenv("LLM_HTTP_TIMEOUT", "10"))
    LLM_MAX_RETRIES: int = int(os.getenv("LLM_MAX_RETRIES", "2"))
    LLM_MODEL: str = os.getenv("LLM_MODEL", "gpt-3.5-turbo")
    LLM_TEMPERATURE: float = float(os.getenv("LLM_TEMPERATURE", "0"))

    # ---------- Alias de compatibilidad (legacy) ----------
    # Si existen variables OPENAI_* en el entorno, se priorizan; si no, usan las LLM_*
    OPENAI_MODEL: str = os.getenv("OPENAI_MODEL") or os.getenv("LLM_MODEL", "gpt-3.5-turbo")
    OPENAI_API_BASE: str = os.getenv("OPENAI_API_BASE") or os.getenv("LLM_API_BASE", "https://api.openai.com/v1")
    OPENAI_HTTP_TIMEOUT: int = int(os.getenv("OPENAI_HTTP_TIMEOUT") or os.getenv("LLM_HTTP_TIMEOUT", "10"))
    OPENAI_MAX_RETRIES: int = int(os.getenv("OPENAI_MAX_RETRIES") or os.getenv("LLM_MAX_RETRIES", "2"))
    OPENAI_TEMPERATURE: float = float(os.getenv("OPENAI_TEMPERATURE") or os.getenv("LLM_TEMPERATURE", "0"))

settings = _Settings()

__all__ = [
    "BASE_DIR",
    "DATA_DIR",
    "CONVERSATION_HISTORY_DIR",
    "TAKEOVER_FILE",
    "OPENAI_API_KEY",
    "HEYOO_TOKEN",
    "ENV",
    "settings",
    # Webhook / Meta
    "VERIFY_TOKEN",
    "APP_SECRET",
    "HEYOO_PHONE_ID",
    "OWNER_PHONE_NUMBER",
    "SYSTEM_PROMPT_FILE",
    # Drive / Productos
    "SERVICE_ACCOUNT_FILE",
    "PRODUCT_LIST_FILE_ID",
    "CATALOG_PDF_LINK",
    "PRODUCTS_CACHE_FILE",
    # LLM
    "LLM_API_BASE",
    "LLM_HTTP_TIMEOUT",
    "LLM_MAX_RETRIES",
    "LLM_MODEL",
    "LLM_TEMPERATURE",
    # Alias legacy
    "OPENAI_MODEL",
    "OPENAI_API_BASE",
    "OPENAI_HTTP_TIMEOUT",
    "OPENAI_MAX_RETRIES",
    "OPENAI_TEMPERATURE",
]
