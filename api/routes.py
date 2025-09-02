from fastapi import APIRouter, HTTPException, Request
from heyoo import WhatsApp
from typing import Dict, Any, Tuple

from core.settings import HEYOO_PHONE_ID, HEYOO_TOKEN, OWNER_PHONE_NUMBER
from core.logger import LoggerManager
from core.structured_parser import llm_update_state
from models.schemas import MessageRequest
from services.security import verify_webhook_signature
from services.conversation import conversation_service
from services.llm_client import llm_client
from services.llm_dispatcher import get_llm_response
from services.validators import (
    validate_message_content,
    validate_phone_country,
    detect_prompt_injection,
    es_nombre_valido,
    is_real_name_with_gpt
)
from services.user_profiles import extract_name_with_llm
from services.audio_processing import audio_processor

# <<< NUEVO: flujo de pasos >>>
from core.steps import init_state_for_dni, compute_reply, QUESTION_TEXT

FORM_STATE: Dict[str, Any] = {}

class WhatsAppRouter:
    def __init__(self):
        """Initialize the WhatsApp router with all required services."""
        self.router = APIRouter()
        self.wa_client = WhatsApp(token=HEYOO_TOKEN, phone_number_id=HEYOO_PHONE_ID)
        self.log = LoggerManager(name="routes", level="INFO", log_to_file=False).get_logger()
        self._register_routes()
        
    def _register_routes(self):
        self.router.get("/webhook")(self.verify_webhook)
        self.router.post("/webhook")(self.heyoo_webhook)
        self.router.post("/send")(self.send_manual_message)
        
    async def verify_webhook(self, request: Request) -> Any:
        params = request.query_params
        if params.get("hub.verify_token") == "HolaAI":
            return int(params.get("hub.challenge"))
        return "Token inválido", 403
    
    async def _handle_status_message(self, value: Dict[str, Any]) -> Tuple[Dict[str, str], int]:
        status_entry = value["statuses"][0]
        status = status_entry.get("status")
        message_id = status_entry.get("id")
        recipient_id = status_entry.get("recipient_id")
        timestamp = status_entry.get("timestamp")

        self.log.debug(f"📩 Status recibido:")
        self.log.debug(f"  - Mensaje ID: {message_id}")
        self.log.debug(f"  - Estado: {status}")
        self.log.debug(f"  - Destinatario: {recipient_id}")
        self.log.debug(f"  - Timestamp: {timestamp}")

        return {"status": "status_logged"}, 200
    
    async def _process_message(self, message_entry: Dict[str, Any], sender_phone: str) -> str:
        if message_entry.get("type") != "text":
            if message_entry.get("type") == "audio":
                media_id = message_entry["audio"]["id"]
                return await audio_processor.process_audio_message(media_id)
            elif message_entry.get("type") == "reaction":
                return "reaction"
            else:
                self.log.warning(f"⚠️ Mensaje no sorportado recibido de {sender_phone} tipo: {message_entry.get('type')}")
                self.wa_client.send_message(
                    "No puedo procesar este tipo de mensaje. ¿Podrías enviarme un mensaje de texto?",
                    sender_phone
                )
            return "unsupported"
        return message_entry["text"]["body"]
    
    async def is_valid_dni(self, message: str) -> str | None:
        dni = message.replace(" ", "").replace(".", "").upper()
        if 6 <= len(dni) <= 12:
            return dni
        else:
            return None

    async def heyoo_webhook(self, request: Request) -> Tuple[Dict[str, str], int]:
        header_signature = request.headers.get("X-Hub-Signature-256") or request.headers.get("X-Hub-Signature")
        body = await request.body()

        # if not verify_webhook_signature(body, header_signature):
        #     self.log.error("🚨 Webhook con firma inválida bloqueado")
        #     raise HTTPException(status_code=403, detail="Invalid signature")

        try:
            data = await request.json()
            value = data["entry"][0]["changes"][0]["value"]

            # 1) Status
            if "statuses" in value:
                return await self._handle_status_message(value)

            # 2) Debe haber messages
            if "messages" not in value:
                self.log.warning("⚠️ Webhook sin 'messages' ni 'statuses'. Ignorando.")
                return {"status": "ignored"}, 200

            # 3) Info básica
            message_entry = value["messages"][0]
            sender_phone = message_entry["from"]  
            
            sender_phone = "542616463629"

            # 4) Validaciones
            validation_country = validate_phone_country(sender_phone, self.wa_client)
            if not validation_country["valid"]:
                return {"status": validation_country["status"]}, 200

            user_message = await self._process_message(message_entry, sender_phone)
            if user_message in ["reaction", "unsupported"]:
                return {"status": f"{user_message}_received"}, 200

            if detect_prompt_injection(user_message):
                self.log.warning(f"🚨 Intento de Prompt Injection detectado de {sender_phone}")
                self.wa_client.send_message(
                    "Tu mensaje no puede ser procesado. ¿Podrías reformularlo?",
                    sender_phone
                )
                return {"status": "prompt_injection_blocked"}, 200

            validation_content = validate_message_content(user_message, sender_phone, self.wa_client)
            if not validation_content["valid"]:
                return {"status": validation_content["status"]}, 200

            profile_info = value.get("contacts", [{}])[0].get("profile", {})
            user_name = profile_info.get("name")

            # 5) Onboarding por estado
            stage = conversation_service.get_stage(sender_phone)
            if stage is None:
                conversation_service.set_stage(sender_phone, "awaiting_dni")
                self.wa_client.send_message(
                    "¡Hola! Soy tu médico anestesiólogo y voy a realizarte unas preguntas para completar tu ficha anestesiológica.",
                    sender_phone,
                )
                self.wa_client.send_message("Para iniciar, por favor ingresá tu DNI:", sender_phone)
                return {"status": "greeted_and_requested_dni"}, 200

            if stage == "awaiting_dni":
                dni = await self.is_valid_dni(user_message)
                if not dni:
                    self.wa_client.send_message("Por favor, ingresá un DNI válido (solo números, sin puntos).", sender_phone)
                    return {"status": "dni_reprompted"}, 200

                conversation_service.rename_conversation_file(sender_phone, dni)
                conversation_service.set_user_key(sender_phone, dni)
                conversation_service.set_stage(sender_phone, "triage")

                FORM_STATE[dni] = init_state_for_dni()
                self.log.debug(f"Conversación asociada a DNI {dni}")
                self.wa_client.send_message(f"¡Gracias! Registré tu DNI: {dni}.", sender_phone)
                self.wa_client.send_message(QUESTION_TEXT["alergias"], sender_phone)
                return {"status": "dni_registered"}, 200

            # 6) TRIAGE
            key = conversation_service.get_user_key(sender_phone) or sender_phone
            if conversation_service.get_stage(sender_phone) != "triage":
                conversation_service.set_stage(sender_phone, "triage")

            current_state = FORM_STATE.get(key, {})
            updated_state = llm_update_state(user_message, current_state)
            FORM_STATE[key] = updated_state  # guardamos primero

            # Delegar decisión de avanzar/repreguntar al motor de pasos
            reply_msg = compute_reply(current_state, updated_state)
            self.wa_client.send_message(reply_msg, sender_phone)
            return {"status": "responded"}, 200

        except Exception as e:
            self.log.exception(f"🚨 Error procesando webhook: {e}")
            return {"status": "error_processing_webhook"}, 500

    async def send_manual_message(self, request: MessageRequest) -> Dict[str, Any]:
        try:
            self.wa_client.send_message(request.message, request.to)
            conversation_service.add_to_conversation_history(request.to, "assistant", request.message)
            return {"success": True, "message": "Mensaje enviado correctamente"}
        except Exception as e:
            self.log.error(f"⚠️ Error enviando mensaje manual: {e}")
            raise HTTPException(status_code=500, detail=f"No se pudo enviar el mensaje: {str(e)}")

# Create router instance
router = WhatsAppRouter().router
