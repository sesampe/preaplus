from fastapi import APIRouter, Request
from services.validators import validate_phone_country, validate_message_content
from services.security import verify_webhook_signature
from core.settings import HEYOO_PHONE_ID, HEYOO_TOKEN, LLM_PROVIDER
from core.logger import LoggerManager  # 🚀 Logger agregado
from heyoo import WhatsApp

router = APIRouter()

wa_client = WhatsApp(token=HEYOO_TOKEN, phone_number_id=HEYOO_PHONE_ID)

# Instanciar el logger
log = LoggerManager(name="health", level="INFO", log_to_file=False).get_logger()

# Funciones placeholder (a desarrollar)
def check_google_drive() -> bool:
    """Verifica conectividad con Google Drive."""
    # TODO: Implementar ping real a Drive
    return True

def check_whatsapp_api() -> bool:
    """Verifica conectividad con WhatsApp API."""
    # TODO: Implementar ping real a WhatsApp
    return True

def check_llm_api() -> bool:
    """Verifica conectividad con el proveedor de LLM configurado."""
    if LLM_PROVIDER == "claude":
        # TODO: Implementar chequeo real a Claude
        return True
    elif LLM_PROVIDER == "openai":
        # TODO: Implementar chequeo real a OpenAI
        return True
    else:
        log.warning(f"⚠️ LLM Provider desconocido: {LLM_PROVIDER}")
        return False

def check_disk_space() -> bool:
    """Verifica espacio en disco del servidor."""
    # TODO: Implementar chequeo real de espacio
    return True

@router.get("/health", tags=["Health"])
def healthcheck():
    """
    Healthcheck avanzado (estructura flexible para diferentes proveedores de LLM).
    """
    log.info("🔍 Healthcheck básico ejecutado")
    return {
        "status": "ok",
        "services": {
            "google_drive": check_google_drive(),
            "whatsapp_api": check_whatsapp_api(),
            "llm_provider": LLM_PROVIDER,
            "llm_api_status": check_llm_api(),
            "disk_space_ok": check_disk_space(),
        }
    }

@router.post("/health/full", tags=["Health"])
async def full_healthcheck(request: Request):
    """Endpoint de testing para validar flujo completo del webhook."""
    results = {}

    try:
        header_signature = request.headers.get("X-Hub-Signature-256") or request.headers.get("X-Hub-Signature")
        body = await request.body()

        # 1. Validar firma
        if not verify_webhook_signature(body, header_signature):
            log.error("🚨 Firma inválida en health/full")
            results["signature"] = "invalid"
            return {"healthcheck": results}

        results["signature"] = "valid"

        # 2. Parsear JSON
        data = await request.json()
        message_entry = data["entry"][0]["changes"][0]["value"]["messages"][0]
        sender_phone = message_entry["from"]

        results["parsing"] = "success"

        # 3. Validar país
        validation_country = validate_phone_country(sender_phone, wa_client)
        if not validation_country["valid"]:
            log.warning(f"⚠️ Validación de país fallida para {sender_phone}")
            results["country_validation"] = "failed"
            return {"healthcheck": results}
        results["country_validation"] = "passed"

        # 4. Validar tipo de mensaje
        message_type = message_entry.get("type")
        if message_type != "text":
            log.warning(f"⚠️ Tipo de mensaje no soportado en health/full: {message_type}")
            results["message_type_validation"] = "failed"
            return {"healthcheck": results}
        results["message_type_validation"] = "passed"

        # 5. Validar contenido del mensaje
        user_message = message_entry["text"]["body"]
        validation_content = validate_message_content(user_message, sender_phone, wa_client)
        if not validation_content["valid"]:
            log.warning(f"⚠️ Validación de contenido fallida en health/full para {sender_phone}")
            results["content_validation"] = "failed"
            return {"healthcheck": results}
        results["content_validation"] = "passed"

        results["final_status"] = "ok"
        log.info("✅ Healthcheck completo exitoso")
        return {"healthcheck": results}

    except Exception as e:
        log.error(f"❌ Excepción en health/full: {str(e)}")
        results["exception"] = str(e)
        return {"healthcheck": results}
