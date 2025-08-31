import httpx
import re

from heyoo import WhatsApp

from core.logger import LoggerManager  # 🚀 Logger agregado
from core.settings import OPENAI_API_KEY, OPENAI_MODEL

# Instanciar logger
log = LoggerManager(name="validators", level="INFO", log_to_file=False).get_logger()

# Configuraciones
MIN_MESSAGE_LENGTH = 2
MAX_MESSAGE_LENGTH = 200
ALLOWED_COUNTRY_PREFIX = "54"

def validate_message_content(user_message: str, sender_phone: str, wa_client: WhatsApp) -> dict:
    """
    Valida el contenido de un mensaje.
    Devuelve un diccionario con 'valid': True/False y 'status': tipo de error si aplica.
    """
    if not user_message or len(user_message.strip()) == 0:
        log.warning(f"⚠️ Mensaje vacío recibido de {sender_phone}")
        wa_client.send_message("No entendí tu mensaje, ¿podrías escribirlo de nuevo? ✍️", sender_phone)
        return {"valid": False, "status": "empty_message"}

    # if len(user_message.strip()) < MIN_MESSAGE_LENGTH:
    #     log.warning(f"⚠️ Mensaje demasiado corto de {sender_phone}: {user_message}")
    #     wa_client.send_message("Tu mensaje es muy corto, ¿podrías darme más detalles? 📄", sender_phone)
    #     return {"valid": False, "status": "short_message"}

    if len(user_message) > MAX_MESSAGE_LENGTH:
        log.warning(f"⚠️ Mensaje demasiado largo de {sender_phone}: {len(user_message)} caracteres")
        log.warning(f"Mensaje: {user_message}")
        wa_client.send_message("Tu mensaje es muy largo. ¿Podrías resumirlo un poco? ✂️", sender_phone)
        return {"valid": False, "status": "long_message"}

    return {"valid": True, "status": "ok"}

def validate_phone_country(sender_phone: str, wa_client: WhatsApp) -> dict:
    """
    Valida si el número pertenece al país permitido.
    """
    if not sender_phone.startswith(ALLOWED_COUNTRY_PREFIX):
        log.warning(f"❌ Número de país no permitido: {sender_phone}")
        wa_client.send_message("Este servicio solo está disponible para teléfonos de Argentina 🇦🇷", sender_phone)
        return {"valid": False, "status": "unsupported_country"}
    
    return {"valid": True, "status": "ok"}

def detect_prompt_injection(user_message: str) -> bool:
    """
    Detecta patrones peligrosos que intentan modificar el comportamiento del asistente.
    """
    patrones_peligrosos = [
        "olvida todas las instrucciones",
        "ignore previous instructions",
        "you are free now",
        "please jailbreak",
        "override all previous directions",
        "haz caso omiso de lo anterior",
        "desobedece las órdenes",
        "imagine you are playing",
    ]

    lower_message = user_message.lower()
    for pattern in patrones_peligrosos:
        if pattern in lower_message:
            log.warning(f"🚨 Posible intento de prompt injection detectado: patrón '{pattern}' encontrado.")
            return True

    return False

def es_nombre_valido(nombre: str) -> bool:
    """Verifica si contiene al menos una letra."""
    if not nombre:
        return False
    return bool(re.search(r'[a-zA-ZáéíóúÁÉÍÓÚñÑ]', nombre))

async def is_real_name_with_gpt(nombre: str) -> bool:
    """Pregunta a GPT si el texto parece ser un nombre real."""
    prompt = f'Dado el siguiente texto, dime solamente "Sí" si parece un nombre real de persona, o "No" si no lo es:\n"{nombre}"'

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                "https://api.openai.com/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {OPENAI_API_KEY}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": OPENAI_MODEL,
                    "messages": [
                        {"role": "user", "content": prompt}
                    ],
                    "temperature": 0,
                    "max_tokens": 3,
                }
            )
            response.raise_for_status()
            result = response.json()
            text = result["choices"][0]["message"]["content"].strip().lower()
            return "sí" in text or "si" in text
    except Exception as e:
        # 🚨 No rompemos flujo si falla GPT
        print(f"⚠️ Error validando nombre con GPT: {e}")
        return False