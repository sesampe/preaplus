# settings.py
import os
from typing import Optional

class Settings:
    ENV: str = os.getenv("ENV", "dev")

    # LLM
    OPENAI_API_KEY: Optional[str] = os.getenv("OPENAI_API_KEY")
    LLM_API_BASE: str = os.getenv("LLM_API_BASE", "https://api.openai.com/v1")
    LLM_MODEL: str = os.getenv("LLM_MODEL", "gpt-4o-mini")
    LLM_HTTP_TIMEOUT: float = float(os.getenv("LLM_HTTP_TIMEOUT", "12.0"))
    LLM_MAX_RETRIES: int = int(os.getenv("LLM_MAX_RETRIES", "2"))
    LLM_TEMPERATURE: float = float(os.getenv("LLM_TEMPERATURE", "0.2"))

    # Server
    PORT: int = int(os.getenv("PORT", "8000"))
    

settings = Settings()
