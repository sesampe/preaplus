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
        """Initialize the WhatsApp router with all required services.""" # DEFINE RUTAS
        self.router = APIRouter()
        self.wa_client = WhatsApp(token=HEYOO_TOKEN, phone_number_id=HEYOO_PHONE_ID)
        self.log = LoggerManager(name="routes", level="INFO", log_to_file=False).get_logger()
        
        # Register routes
        self._register_routes()
        
    def _register_routes(self): #define endpoints que te manda whatsapp a la app
        """Register all routes with the router."""
        self.router.get("/webhook")(self.verify_webhook)
        self.router.post("/webhook")(self.heyoo_webhook)
        self.router.post("/send")(self.send_manual_message)
        
    async def verify_webhook(self, request: Request) -> Any: #verifica que webhook este OK
        """Verify webhook endpoint for WhatsApp API setup."""
        params = request.query_params
        if params.get("hub.verify_token") == "HolaAI":
            return int(params.get("hub.challenge"))
        return "Token inválido", 403
    
    async def _handle_status_message(self, value: Dict[str, Any]) -> Tuple[Dict[str, str], int]: #checkea que mensaje que envias llegue, si se lee,etc
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
    
    async def _process_message(self, message_entry: Dict[str, Any], sender_phone: str) -> str: #ANALIZA QUE TIPO DE MENSAJE ES
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
    
    async def is_valid_dni(self, message: str) -> str | None:
        dni = message.replace(" ", "").replace(".", "").upper()
        if 6 <= len(dni) <= 12:
            return dni
        else:
            return None

    
    #async def _handle_new_user(self, sender_phone: str, user_name: str) -> str: #analiza si es nuevo paciente o no, para ver como lo saluda.
    #    """Handle new user interaction and return appropriate greeting."""
    #    sender_phone = "2616463629"
    #    if not conversation_service.get_name_from_conversation(sender_phone):
    #        if not conversation_service.get_conversation_history(sender_phone):
    #            if user_name and es_nombre_valido(user_name):
    #                if await is_real_name_with_gpt(user_name):
    #                    conversation_service.set_customer_name(sender_phone, user_name)
    #                    return f"¡Hola {user_name}! Soy tu medico anestesiologo y voy a realizarte algunas preguntas para completar tu ficha anestesiologica"
    #            return "¡Hola! Soy tu medico anestesiologo y voy a realizarte algunas preguntas para completar tu ficha anestesiologica"
    #    return ""



    async def heyoo_webhook(self, request: Request) -> Tuple[Dict[str, str], int]:
        """Handle incoming webhook from WhatsApp."""
        # Verify signature (se fija si la firma de quien manda la solicitud es la permitida -Meta-)
        header_signature = request.headers.get("X-Hub-Signature-256") or request.headers.get("X-Hub-Signature")
        body = await request.body()

        # if not verify_webhook_signature(body, header_signature):
        #    self.log.error("🚨 Webhook con firma inválida bloqueado")
        #    raise HTTPException(status_code=403, detail="Invalid signature")

        try:
            data = await request.json()
            value = data["entry"][0]["changes"][0]["value"]

            # Handle status messages (SE FIJA SI ES UN ESTADO DE UN MENSAJE, O UN MENSAJE.)
            if "statuses" in value:
                return await self._handle_status_message(value)

            # Validate message exists
            if "messages" not in value:
                self.log.warning("⚠️ Webhook sin 'messages' ni 'statuses'. Ignorando.")
                return {"status": "ignored"}, 200

            # Process message (EXTRAE DATOS DEL MENSAJE: NUMERO Y MENSAJE --> PARA HACER FUTURAS VALIDACIONES)
            message_entry = value["messages"][0]
            sender_phone = message_entry["from"]

            # Validate phone
            validation_country = validate_phone_country(sender_phone, self.wa_client)
            if not validation_country["valid"]:
                return {"status": validation_country["status"]}, 200

            # Process message content (DECIDE QUE HACER SEGN TIPO DE MENSAJE QUE ARROJO _PROCESS_MESSAGE)
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

            # Get user profile and handle new user (MIRA DATOS A VER SI SE PUEDE SACAR UN NOMBRE)
            profile_info = value.get("contacts", [{}])[0].get("profile", {})
            user_name = profile_info.get("name")
            
            # Saludo solo si es conversación nueva
            if not conversation_service.get_conversation_history(sender_phone):
                self.wa_client.send_message(
                    "¡Hola! Soy tu médico anestesiólogo y voy a realizarte unas preguntas para completar tu ficha anestesiológica:",
                    sender_phone
                )
                self.wa_client.send_message("PARA INICIAR, INGRESE SU DNI:", sender_phone)

            # Intentar leer un DNI en este mensaje
            dni = await self.is_valid_dni(user_message)

            if dni:
                # Renombrar el archivo de conversación al DNI y seguir usando el DNI como key
                conversation_service.rename_conversation_file(sender_phone, dni)
                key = dni
                self.log.debug(f"JSON cambiado de nombre a: {dni}")
            else:
                # Si aún no tenemos DNI registrado para este usuario, pedirlo y cortar
                if not conversation_service.has_conversation_key(sender_phone) and not conversation_service.has_conversation_key_for_user(sender_phone):
                    self.wa_client.send_message("POR FAVOR, INGRESE DNI VÁLIDO:", sender_phone)
                    return {"status": "dni_requested"}, 200
                # Si ya lo teníamos de antes, recuperarlo
                key = conversation_service.get_key_for_user(sender_phone)

            # Obtener respuesta del LLM con el historial bajo la key correcta
            try:
                self.log.info(f"🧠 Consultando modelo IA para key={key}")
                response_text = await get_llm_response(
                    user_message,
                    conversation_service.get_conversation_history(key)
                )
            except Exception as e:
                self.log.error(f"⚠️ Error consultando IA: {e}")
                response_text = "Estamos experimentando dificultades. ¿Querés que te conecte con una persona?"

            conversation_service.add_to_conversation_history(key, "assistant", response_text)
            self.wa_client.send_message(response_text, sender_phone)
            return {"status": "responded"}, 200

        except Exception as e: # (SI HUBO CUALQUIER ERROR EN ESTE def, DA UN LOG PARA QUE LO VEAMOS Y AVISA A WHATSAPP ASI NO SIGUE AVISANDO)
            self.log.error(f"⚠️ Error al parsear mensaje o status: {e}")
            try:
                self.log.error(f"Payload recibido: {data['entry'][0]['changes'][0]['value']}")
            except:
                self.log.error("No se pudo imprimir el valor del webhook recibido.")
            return {"status": "ignored"}, 200

    async def send_manual_message(self, request: MessageRequest) -> Dict[str, Any]: #ESTE ES UN def POR SI QUEREMOS MANDAR UN MENSAJE MANUALMENTE DESDE LA API
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
