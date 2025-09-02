#ESTE ES EL PUENTE ENTRE BOT Y LOS MODELOS DE LENGUAJE
#MANEJA ESAS COMUNICACIONES, CONTROLA ERRORES, ETC.

import httpx
import asyncio
from typing import List, Dict, Any, Optional
#import openai
from heyoo import WhatsApp

from core.settings import (
    OPENAI_API_KEY,
    OPENAI_MODEL,
    CLAUDE_API_KEY,
    CLAUDE_MODEL,
    HEYOO_TOKEN,
    HEYOO_PHONE_ID,
    OWNER_PHONE_NUMBER,
    SYSTEM_PROMPT,
    PREANESTHESIA_SCHEMA
)
from core.logger import LoggerManager

def _sanitize_history(history):
    """
    Deja solo roles 'user' y 'assistant', evita contaminar con 'system'
    y fuerza a que siempre exista 'content' (string).
    """
    out = []
    for m in history or []:
        role = m.get("role")
        if role in ("user", "assistant"):
            out.append({"role": role, "content": m.get("content", "")})
    return out


class LLMClient:
    """Cliente para interactuar con APIs de modelos de lenguaje (OpenAI GPT y Anthropic Claude)."""

    _instance = None

    def __new__(cls): #CREA SINGLETON, PARA QUE SE MANEJE SIEMPRE CON LA MISMA CONFIGURACION.
        """Implementación de singleton."""
        if cls._instance is None:
            cls._instance = super(LLMClient, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        """Inicializa servicios y configuración."""
        if self._initialized:
            return

        self.log = LoggerManager(name="llm_client", level="INFO", log_to_file=False).get_logger() 
        #CREA UN "CUADERNO" DONDE ANOTAR LO QUE HACE EL LLM CON LOS SIGUIENTES DATOS:
        self.wa_client = WhatsApp(token=HEYOO_TOKEN, phone_number_id=HEYOO_PHONE_ID)
        self.http_timeout = 30.0
        self.max_retries = 5
        self._initialized = True

        self.log.info(f"SYSTEM_PROMPT len={len(SYSTEM_PROMPT)}")
        self.log.debug(f"Preview prompt: {SYSTEM_PROMPT[:200]}")


    # ABRE UN "TELEFONO" Y ENVIA EL JSON + SE FIJA SI HAY ERROR. TRADUCE LO QUE RESPONDE EL LLMClient A FORMATO JSON.
    async def _make_http_request(self, url: str, headers: Dict[str, str], json_data: Dict[str, Any]) -> Dict[str, Any]:
        """Hace un POST HTTP con manejo de timeout y devuelve el JSON."""
        async with httpx.AsyncClient(timeout=self.http_timeout) as client:
            response = await client.post(url, headers=headers, json=json_data)
            response.raise_for_status()
            return response.json()

    # -------------------------
    # Llamadas al modelo (Claude)
    # -------------------------
    async def ask_claude(self, user_message: str, conversation_history: List[Dict[str, Any]]) -> str:
        """Envía la conversación a Claude y devuelve el texto de respuesta."""
        # Sanear historial: solo user/assistant
        messages = _sanitize_history(conversation_history)
        # Agregar último user
        messages.append({"role": "user", "content": user_message})

        try:
            self.log.info("🧠 Llamando a Claude API")
            response = await self._make_http_request(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": CLAUDE_API_KEY,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json"
                },
                json_data={
                    "model": CLAUDE_MODEL,
                    "max_tokens": 500,
                    # Mantener system separado en Claude
                    "system": SYSTEM_PROMPT,
                    "messages": messages
                }
            )
            self.log.info("✅ Respuesta recibida de Claude")
            return response["content"][0]["text"]
        except Exception as e:
            self.log.error(f"❌ Error llamando a Claude API: {e}")
            return "No puedo responder en este momento. ¿Querés que te conecte con una persona?"


    # -------------------------
    # Llamadas al modelo (OpenAI)
    # -------------------------
    async def ask_gpt(self, user_message: str, conversation_history: List[Dict[str, Any]]) -> str:
        """Envía la conversación a GPT con reintentos básicos y devuelve el texto de respuesta."""
        # Siempre inyectar system UNA vez
        messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        # Historial saneado (sin 'system' internos)
        messages.extend(_sanitize_history(conversation_history))
        # Último user
        messages.append({"role": "user", "content": user_message})

        for attempt in range(self.max_retries):
            try:
                response = await self._make_http_request(
                    "https://api.openai.com/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {OPENAI_API_KEY}",
                        "Content-Type": "application/json",
                    },
                    json_data={
                        "model": OPENAI_MODEL,
                        "messages": messages,
                        "temperature": 0.5,
                        "max_tokens": 500,
                    }
                )
                return response["choices"][0]["message"]["content"]
            except httpx.HTTPStatusError as e:
                if e.response.status_code == 429:
                    wait_time = 2 ** attempt
                    self.log.warning(f"⏳ Rate limit alcanzado, reintentando en {wait_time} segundos...")
                    await asyncio.sleep(wait_time)
                else:
                    self.log.error(f"❌ Error consultando OpenAI: {e}")
                    break
            except Exception as e:
                self.log.error(f"❌ Error inesperado con OpenAI: {e}")
                break

        # Fallback a Claude
        self.log.warning(f"⚠️ Fallaron {self.max_retries} intentos con OpenAI. Probando fallback a Claude...")
        try:
            claude_response = await self.ask_claude(user_message, conversation_history)
            self.log.info("✅ Claude respondió exitosamente en fallback.")
            return claude_response
        except Exception as e:
            self.log.error(f"❌ Error también consultando Claude: {e}")
            return "Actualmente estamos experimentando dificultades. ¿Querés que te conecte con una persona?"


    # -------------------------
    # Utilidades simples (resúmenes)
    # -------------------------
    async def call_llm_simple(self, prompt: str, use_claude: bool = False) -> str:
        """Llamado simple a un LLM sin system prompt explícito."""
        if use_claude:
            return await self._call_claude_simple(prompt)
        return await self._call_gpt_simple(prompt)

    async def _call_claude_simple(self, prompt: str) -> str:
        """Llamado simple a Claude."""
        try:
            response = await self._make_http_request(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": CLAUDE_API_KEY,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json"
                },
                json_data={
                    "model": CLAUDE_MODEL,
                    "max_tokens": 500,
                    "system": "Eres un asistente que realiza tareas técnicas de resumen de texto.",
                    "messages": [{"role": "user", "content": prompt}]
                }
            )
            return response["content"][0]["text"].strip()
        except Exception as e:
            self.log.error(f"❌ Error en llamada simple a Claude: {e}")
            return "No se pudo procesar."

    async def _call_gpt_simple(self, prompt: str) -> str:
        """Llamado simple a GPT con reintentos."""
        for attempt in range(self.max_retries):
            try:
                response = await self._make_http_request(
                    "https://api.openai.com/v1/chat/completions",
                    headers={"Authorization": f"Bearer {OPENAI_API_KEY}"},
                    json_data={
                        "model": OPENAI_MODEL,
                        "messages": [{"role": "user", "content": prompt}],
                        "temperature": 0.2,
                        "max_tokens": 500,
                    }
                )
                return response["choices"][0]["message"]["content"].strip()
            except httpx.HTTPStatusError as e:
                if e.response.status_code == 429:
                    wait_time = 2 ** attempt
                    self.log.warning(f"⏳ Rate limit alcanzado, reintentando en {wait_time} segundos...")
                    await asyncio.sleep(wait_time)
                else:
                    self.log.error(f"❌ Error consultando OpenAI: {e}")
                    break
            except Exception as e:
                self.log.error(f"❌ Error inesperado con OpenAI: {e}")
                break

        # Fallback a Claude
        self.log.warning(f"⚠️ Fallaron {self.max_retries} intentos con OpenAI. Probando fallback a Claude...")
        return await self._call_claude_simple(prompt)

    async def get_summary_from_conversation_history(self, conversation_history: List[Dict[str, Any]]) -> str:
        """Genera un resumen corto del historial."""
        if not conversation_history:
            return "Sin historial de conversación."

        prompt = "Resume esta conversación de manera concisa:\n\n"
        for msg in conversation_history[-20:]:
            prompt += f"{msg['role']}: {msg['content']}\n"

        return await self.call_llm_simple(prompt)

    # -------------------------
    # Compatibilidad y notificaciones
    # -------------------------
    @staticmethod
    def confirmar_pedido(message: str) -> bool:
        """(Compat) Antes confirmaba pedidos. Ahora siempre False para no disparar lógica de ventas."""
        return False
    
    ############################## HAY QUE ARMAR EL PROMPT PARA QUE ME ARROJE DIRECTAMENTE UN JSON #################################
    #def get_info()->json:
    #    client.completion(mensajes, PREANESTHESIA_SCHEMA).parse

    async def notify_owner(self, customer_phone: str, name: str, summary: str, order_summary: str = None) -> str:
        """Notifica al owner sobre una conversación que requiere atención (sin info de 'pedido')."""
        message = f"🚨 *Atención requerida*\n\nCliente: {customer_phone}\n\nNombre: {name}\n\nResumen:\n{summary}\n"
        try:
            self.wa_client.send_message(
                message=message,
                recipient_id=OWNER_PHONE_NUMBER
            )
            self.log.info(f"✅ Notificación enviada al dueño sobre {customer_phone}")
        except Exception as e:
            self.log.error(f"❌ Error notificando al dueño: {e}")
        return message

# Instancia singleton
llm_client = LLMClient()
