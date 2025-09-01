from fastapi import APIRouter, HTTPException, Request
from heyoo import WhatsApp
from typing import Dict, Any, Tuple

from core.settings import HEYOO_PHONE_ID, HEYOO_TOKEN, OWNER_PHONE_NUMBER
from core.logger import LoggerManager
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

class WhatsAppRouter:
    def __init__(self):
        """Initialize the WhatsApp router with all required services."""
        self.router = APIRouter()
        self.wa_client = WhatsApp(token=HEYOO_TOKEN, phone_number_id=HEYOO_PHONE_ID)
        self.log = LoggerManager(name="routes", level="INFO", log_to_file=False).get_logger()
        
        # Register routes
        self._register_routes()
        
    def _register_routes(self):
        """Register all routes with the router."""
        self.router.get("/webhook")(self.verify_webhook)
        self.router.post("/webhook")(self.heyoo_webhook)
        self.router.post("/send")(self.send_manual_message)
        
    async def verify_webhook(self, request: Request) -> Any:
        """Verify webhook endpoint for WhatsApp API setup."""
        params = request.query_params
        if params.get("hub.verify_token") == "HolaAI":
            return int(params.get("hub.challenge"))
        return "Token inválido", 403
    
    async def _handle_status_message(self, value: Dict[str, Any]) -> Tuple[Dict[str, str], int]:
        """Handle status message from WhatsApp."""
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
        """Process incoming message and return the message content."""
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
    
    async def _handle_new_user(self, sender_phone: str, user_name: str) -> str:
        """Handle new user interaction and return appropriate greeting."""
        if not conversation_service.get_name_from_conversation(sender_phone):
            if not conversation_service.get_conversation_history(sender_phone):
                if user_name and es_nombre_valido(user_name):
                    if await is_real_name_with_gpt(user_name):
                        conversation_service.set_customer_name(sender_phone, user_name)
                        return f"¡Hola {user_name}! Soy tu medico anestesiologo y voy a realizarte algunas preguntas para completar tu ficha anestesiologica"
                return "¡Hola! Soy tu medico anestesiologo y voy a realizarte algunas preguntas para completar tu ficha anestesiologica"
        return ""

    async def heyoo_webhook(self, request: Request) -> Tuple[Dict[str, str], int]:
        """Handle incoming webhook from WhatsApp."""
        # Verify signature
        header_signature = request.headers.get("X-Hub-Signature-256") or request.headers.get("X-Hub-Signature")
        body = await request.body()

        #if not verify_webhook_signature(body, header_signature):
        #    self.log.error("🚨 Webhook con firma inválida bloqueado")
        #    raise HTTPException(status_code=403, detail="Invalid signature")

        try:
            data = await request.json()
            value = data["entry"][0]["changes"][0]["value"]

            # Handle status messages
            if "statuses" in value:
                return await self._handle_status_message(value)

            # Validate message exists
            if "messages" not in value:
                self.log.warning("⚠️ Webhook sin 'messages' ni 'statuses'. Ignorando.")
                return {"status": "ignored"}, 200

            # Process message
            message_entry = value["messages"][0]
            sender_phone = message_entry["from"]

            # Validate phone
            validation_country = validate_phone_country(sender_phone, self.wa_client)
            if not validation_country["valid"]:
                return {"status": validation_country["status"]}, 200

            # Process message content
            user_message = await self._process_message(message_entry, sender_phone)
            if user_message in ["reaction", "unsupported"]:
                return {"status": f"{user_message}_received"}, 200

            # Check for prompt injection
            if detect_prompt_injection(user_message):
                self.log.warning(f"🚨 Intento de Prompt Injection detectado de {sender_phone}")
                self.wa_client.send_message(
                    "Tu mensaje no puede ser procesado. ¿Podrías reformularlo?",
                    sender_phone
                )
                return {"status": "prompt_injection_blocked"}, 200

            # Validate message content
            validation_content = validate_message_content(user_message, sender_phone, self.wa_client)
            if not validation_content["valid"]:
                return {"status": validation_content["status"]}, 200

            # Get user profile and handle new user
            profile_info = value.get("contacts", [{}])[0].get("profile", {})
            user_name = profile_info.get("name")
            
            saludo = await self._handle_new_user(sender_phone, user_name)
            if saludo:
                self.wa_client.send_message(saludo, 542616463629)
                conversation_service.add_to_conversation_history(sender_phone, "assistant", saludo)

            # Add user message to history
            conversation_service.add_to_conversation_history(sender_phone, "user", user_message)

            # Try to extract name if not known
            if not conversation_service.get_name_from_conversation(sender_phone):
                if not saludo:
                    if not conversation_service.get_name_tried(sender_phone):
                        self.log.info(f"📝 Nombre no encontrado en conversación para {sender_phone}. Intentando extraer...")
                        detected_name = await extract_name_with_llm(user_message)
                        if detected_name:
                            conversation_service.set_customer_name(sender_phone, detected_name)
                            conversation_service.add_to_conversation_history(
                                sender_phone,
                                "assistant",
                                f"Guardé tu nombre como {detected_name}"
                            )
                            self.log.info(f"📝 Nombre aprendido para {sender_phone}: {detected_name}")
                        else:
                            conversation_service.set_name_tried(sender_phone, True)
                            conversation_service.set_customer_name(sender_phone, None)

            # Check for confirmation of order
            #if llm_client.confirmar_pedido(user_message):
            #    self.log.info(f"📝 Pedido confirmado para {sender_phone}")
            #    self.wa_client.send_message(
            #        "¡Gracias! Tu pedido ha sido confirmado. Nos pondremos en contacto contigo pronto.",
            #        sender_phone
            #    )
            #    order_summary = await llm_client.get_order_summary(conversation_service.get_conversation_history(sender_phone))
            #    self.log.debug(f"📝 Resumen del pedido: {order_summary}")
            #    summary = await llm_client.get_summary_from_conversation_history(conversation_service.get_conversation_history(sender_phone))
            #    name = conversation_service.get_name_from_conversation(sender_phone)
            #    response_text = await llm_client.notify_owner(sender_phone, name, summary, order_summary)
            #    conversation_service.add_to_conversation_history(sender_phone, "assistant", response_text)
            #    conversation_service.set_order_confirmed(sender_phone, order_summary, True)
            #    return {"status": "order_confirmed"}, 200

            # Check for human takeover
            #if llm_client.needs_human_takeover(user_message):
            #    conversation_service.set_human_takeover(sender_phone, True)
            #    self.log.info(f"👤 Activando human takeover para {sender_phone}")
            #    self.wa_client.send_message(
            #        "Una persona se contactará contigo a la brevedad. Mientras tanto puedes consultarme lo que necesites.",
            #        sender_phone
            #    )
            #    summary = await llm_client.get_summary_from_conversation_history(conversation_service.get_conversation_history(sender_phone))
            #    name = conversation_service.get_name_from_conversation(sender_phone)
            #    response_text = await llm_client.notify_owner(sender_phone, name, summary)
            #    conversation_service.add_to_conversation_history(sender_phone, "assistant", response_text)
            #    return {"status": "escalated"}, 200

            # Get AI response
            try:
                self.log.info(f"🧠 Consultando modelo IA para {sender_phone}")
                self.log.info(f"📤 Enviando respuesta a {sender_phone}")
                self.log.info(f"📤 OWNER PHONE NUMBER: {OWNER_PHONE_NUMBER}")
                response_text = await get_llm_response(
                    user_message,
                    conversation_service.get_conversation_history(sender_phone)
                )
            except Exception as e:
                self.log.error(f"⚠️ Error consultando IA: {e}")
                response_text = "Estamos experimentando dificultades. ¿Querés que te conecte con una persona?"

            # Send response
            conversation_service.add_to_conversation_history(sender_phone, "assistant", response_text)
            self.wa_client.send_message(response_text, sender_phone)

            return {"status": "responded"}, 200

        except Exception as e:
            self.log.error(f"⚠️ Error al parsear mensaje o status: {e}")
            try:
                self.log.error(f"Payload recibido: {data['entry'][0]['changes'][0]['value']}")
            except:
                self.log.error("No se pudo imprimir el valor del webhook recibido.")
            return {"status": "ignored"}, 200

    async def send_manual_message(self, request: MessageRequest) -> Dict[str, Any]:
        """Send a manual message to a WhatsApp user."""
        try:
            self.wa_client.send_message(request.message, request.to)
            conversation_service.add_to_conversation_history(request.to, "assistant", request.message)
            return {"success": True, "message": "Mensaje enviado correctamente"}
        except Exception as e:
            self.log.error(f"⚠️ Error enviando mensaje manual: {e}")
            raise HTTPException(status_code=500, detail=f"No se pudo enviar el mensaje: {str(e)}")

# Create router instance
router = WhatsAppRouter().router
