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

FORM_STATE: Dict[str, Any] = {}

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
            
            sender_phone = "542616463629"
            # 1) Si es conversación nueva para este número, inicializá el estado y pedí DNI una sola vez
            stage = conversation_service.get_stage(sender_phone)
            if stage is None:
                conversation_service.set_stage(sender_phone, "awaiting_dni")
                self.wa_client.send_message(
                    "¡Hola! Soy tu médico anestesiólogo y voy a realizarte unas preguntas para completar tu ficha anestesiológica.",
                    sender_phone,
                )
                self.wa_client.send_message("Para iniciar, por favor ingresá tu DNI:", sender_phone)
                return {"status": "greeted_and_requested_dni"}, 200

            # 2) Manejo por estado
            if stage == "awaiting_dni":
                dni = await self.is_valid_dni(user_message)
                if not dni:
                    self.wa_client.send_message("Por favor, ingresá un DNI válido (solo números, sin puntos).", sender_phone)
                    return {"status": "dni_reprompted"}, 200

                # Mapear este teléfono a la key = DNI, renombrar archivo, mover historial si hace falta
                conversation_service.rename_conversation_file(sender_phone, dni)
                conversation_service.set_user_key(sender_phone, dni)
                conversation_service.set_stage(sender_phone, "triage")

                self.log.debug(f"Conversación asociada a DNI {dni}")
                self.wa_client.send_message(f"¡Gracias! Registré tu DNI: {dni}.", sender_phone)
                # Podés seguir con tu primer pregunta clínica aquí y cortar SIN LLM:
                self.wa_client.send_message("¿Tenés alguna alergia a medicamentos o alimentos?", sender_phone)
                return {"status": "dni_registered"}, 200

            # 3) A partir de acá, ya tenemos DNI → usar esa key SIEMPRE
            key = conversation_service.get_user_key(sender_phone) or sender_phone  # fallback defensivo
            if conversation_service.get_stage(sender_phone) != "triage":
                # Si por alguna razón el estado no es triage, forzalo
                conversation_service.set_stage(sender_phone, "triage")

            # >>> SOLO aquí hablamos con el LLM <<<
            # Estado actual (si no tenés persistencia propia):
            current_state = FORM_STATE.get(key, {})

            # 1) Extraer con structured output + merge/normalización
            updated_state = llm_update_state(user_message, current_state)

            # 2) Guardar el nuevo estado (cambiá esto por conversation_service.set_form_state(key, updated_state) si lo tenés)
            FORM_STATE[key] = updated_state

            # 3) Armar confirmación humana breve
            confirms = []
            ant = updated_state.get("antropometria", {})
            prev_ant = (current_state.get("antropometria") or {}) if current_state else {}

            if ant.get("talla_cm") and ant.get("talla_cm") != prev_ant.get("talla_cm"):
                confirms.append(f"Estatura: {int(ant['talla_cm'])} cm")
            if ant.get("peso_kg") and ant.get("peso_kg") != prev_ant.get("peso_kg"):
                confirms.append(f"Peso: {ant['peso_kg']} kg")
            if ant.get("imc") and ant.get("imc") != prev_ant.get("imc"):
                confirms.append(f"IMC: {ant['imc']}")

            alerg = updated_state.get("alergias", {})
            prev_alerg = (current_state.get("alergias") or {}) if current_state else {}
            if alerg.get("tiene_alergias") is True and alerg.get("tiene_alergias") != prev_alerg.get("tiene_alergias"):
                confirms.append("Alergias: sí")
            elif alerg.get("tiene_alergias") is False and alerg.get("tiene_alergias") != prev_alerg.get("tiene_alergias"):
                confirms.append("Alergias: no")

            asa = (updated_state.get("evaluacion_preoperatoria") or {}).get("asa") or updated_state.get("asa")
            prev_asa = (current_state.get("evaluacion_preoperatoria") or {}).get("asa") if current_state else None
            if asa and asa != prev_asa:
                confirms.append(f"ASA: {asa}")

            msg = ("Anoté: " + "; ".join(confirms) + ". ¿Seguimos?") if confirms \
                else "Gracias. ¿Seguimos con la siguiente pregunta?"

            self.wa_client.send_message(msg, sender_phone)
            return {"status": "responded"}, 200


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
