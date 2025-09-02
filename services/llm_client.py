# llm_client.py
import json
import time
from typing import Optional
import httpx

from settings import settings

class LLMClient:
    """
    Cliente HTTP simple contra /v1/chat/completions (OpenAI-compatible).
    Reutiliza httpx.Client, timeout bajo y retries cortos.
    """

    def __init__(self):
        self._client = httpx.Client(
            base_url=settings.LLM_API_BASE,
            headers=self._default_headers(),
            timeout=settings.LLM_HTTP_TIMEOUT,
        )
        self.max_retries = settings.LLM_MAX_RETRIES

    def _default_headers(self):
        headers = {"Content-Type": "application/json"}
        if settings.OPENAI_API_KEY:
            headers["Authorization"] = f"Bearer {settings.OPENAI_API_KEY}"
        return headers

    def call_llm_simple(
        self,
        prompt: str,
        max_tokens: int = 200,
        temperature: float = None,
        model: Optional[str] = None,
    ) -> str:
        """Devuelve el texto del primer choice."""
        body = {
            "model": model or settings.LLM_MODEL,
            "messages": [
                {"role": "system", "content": "Respondé SOLO con el JSON pedido. Sin comentarios."},
                {"role": "user", "content": prompt},
            ],
            "temperature": settings.LLM_TEMPERATURE if temperature is None else temperature,
            "max_tokens": max_tokens,
        }

        last_err = None
        for attempt in range(1 + self.max_retries):
            try:
                resp = self._client.post("/chat/completions", json=body)
                resp.raise_for_status()
                data = resp.json()
                return data["choices"][0]["message"]["content"].strip()
            except Exception as e:
                last_err = e
                # backoff corto
                time.sleep(0.4 * (attempt + 1))
        raise RuntimeError(f"LLM request failed after retries: {last_err}")

# singleton
llm_client = LLMClient()
