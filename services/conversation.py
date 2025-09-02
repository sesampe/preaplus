import os
import json
import time

from typing import List, Dict, Any, Optional
from datetime import datetime

from core.settings import CONVERSATION_HISTORY_DIR, TAKEOVER_FILE
from core.logger import LoggerManager
from models.schemas import ConversationContext

class ConversationService:
    """Service for managing conversations, customer profiles, and interaction contexts."""

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(ConversationService, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        """Initialize the Conversation service (singleton-safe)."""
        if getattr(self, "_initialized", False):
            return

        # Logger del servicio
        self.log = LoggerManager(name="conversation", level="INFO", log_to_file=False).get_logger()

        # Paths / estado
        self._ensure_directories()
        self._base_path = CONVERSATION_HISTORY_DIR  # opcional; útil si querés usarlo en más lugares

        # Config
        self._takeover_expiration = 180  # seconds

        # Estados en memoria
        self._conversation_contexts: Dict[str, ConversationContext] = {}
        self._stages: Dict[str, str] = {}
        self._phone_to_key: Dict[str, str] = {}

        self._initialized = True

    def _ensure_directories(self) -> None:
        os.makedirs(CONVERSATION_HISTORY_DIR, exist_ok=True)

    def _sanitize_phone(self, phone: str) -> str:
        return phone.replace(":", "_").replace("+", "").replace("whatsapp", "")

    def _get_conversation_filepath(self, phone_number: str) -> str:
        filename = self._sanitize_phone(phone_number) + ".json"
        return os.path.join(CONVERSATION_HISTORY_DIR, filename)

    # -----------------------------
    # Conversation STAGES
    # -----------------------------
    def get_stage(self, phone: str) -> Optional[str]:
        return self._stages.get(phone)

    def set_stage(self, phone: str, stage: str) -> None:
        self._stages[phone] = stage

    def set_user_key(self, phone: str, key: str) -> None:
        self._phone_to_key[phone] = key

    def get_user_key(self, phone: str) -> Optional[str]:
        return self._phone_to_key.get(phone)

    def has_history(self, key: str) -> bool:
        """Devuelve True si existe historial no vacío para este key (teléfono o DNI)."""
        path = self._get_conversation_filepath(key)  # ← usar helper en lugar de _base_path crudo
        if not os.path.exists(path):
            return False
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            hist = data.get("history", [])
            return bool(hist)
        except Exception:
            return False

    # -----------------------------
    # Conversation Context Management
    # -----------------------------
    def rename_conversation_file(self, old_phone: str, dni: str) -> str:
        old_path = self._get_conversation_filepath(old_phone)
        new_path = os.path.join(CONVERSATION_HISTORY_DIR, f"{dni}.json")
        if os.path.exists(old_path):
            os.rename(old_path, new_path)
            self.log.info(f"📂 Archivo de conversación renombrado: {old_path} → {new_path}")
        return new_path

    def get_conversation_context(self, phone: str) -> ConversationContext:
        if phone not in self._conversation_contexts:
            self._conversation_contexts[phone] = ConversationContext(
                customer_phone=phone,
                last_message_timestamp=datetime.utcnow()
            )
        return self._conversation_contexts[phone]

    def update_conversation_context(self, phone: str,
                                    intent: Optional[str] = None,
                                    order_id: Optional[str] = None,
                                    human_takeover: Optional[bool] = None) -> ConversationContext:
        context = self.get_conversation_context(phone)
        if intent is not None:
            context.last_intent = intent
        if order_id is not None:
            context.current_order_id = order_id
        if human_takeover is not None:
            context.human_takeover = human_takeover
        context.last_message_timestamp = datetime.utcnow()
        return context

    def clear_conversation_context(self, phone: str) -> None:
        if phone in self._conversation_contexts:
            del self._conversation_contexts[phone]

    # -----------------------------
    # Takeover Management
    # -----------------------------
    def load_takeover_status(self) -> Dict[str, dict]:
        if os.path.exists(TAKEOVER_FILE):
            try:
                with open(TAKEOVER_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
            except json.JSONDecodeError:
                self.log.warning("⚠️ Error al leer el archivo de takeover, devolviendo vacío.")
                return {}
        return {}

    def save_takeover_status(self, status_dict: Dict[str, dict]) -> None:
        active_status = {
            phone: data
            for phone, data in status_dict.items()
            if data.get("active", False)
        }
        try:
            with open(TAKEOVER_FILE, "w", encoding="utf-8") as f:
                json.dump(active_status, f, ensure_ascii=False, indent=2)
            self.log.info(f"💾 Estado de takeover guardado. Usuarios activos: {len(active_status)}")
        except Exception as e:
            self.log.error(f"❌ Error al guardar el archivo de takeover: {e}")

    def is_human_takeover(self, phone_number: str) -> bool:
        status = self.load_takeover_status()
        record = status.get(phone_number)
        if record and record.get("active"):
            timestamp = record.get("timestamp", 0)
            elapsed = time.time() - timestamp
            if elapsed > self._takeover_expiration:
                self.log.warning(f"⚠️ Takeover expirado para {phone_number} después de {elapsed:.1f} segundos")
                self.set_human_takeover(phone_number, False)
                return False
            return True
        return False

    def set_human_takeover(self, phone_number: str, active: bool) -> None:
        current_status = self.load_takeover_status()
        if active:
            current_status[phone_number] = {
                "active": True,
                "timestamp": time.time(),
                "alerted": False
            }
        else:
            if phone_number in current_status:
                del current_status[phone_number]
        self.save_takeover_status(current_status)
        self.log.info(f"🛡️ Takeover {'activado' if active else 'desactivado'} para {phone_number}")

    # -----------------------------
    # Conversation Management
    # -----------------------------
    def load_conversation_file(self, phone_number: str) -> dict:
        filepath = self._get_conversation_filepath(phone_number)
        if os.path.exists(filepath):
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                self.log.error(f"❌ Error al leer conversación para {phone_number}: {e}")
        return {}

    def save_conversation_file(self, phone_number: str, data: dict) -> None:
        filepath = self._get_conversation_filepath(phone_number)
        try:
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            self.log.info(f"💾 Conversación guardada para {phone_number}")
        except Exception as e:
            self.log.error(f"❌ Error al guardar conversación para {phone_number}: {e}")

    def get_name_from_conversation(self, phone_number: str) -> str:
        data = self.load_conversation_file(phone_number)
        if not data:
            return ""
        name = data.get("name", "")
        if not name:
            self.log.warning(f"⚠️ Nombre no encontrado en conversación para {phone_number}")
        return name

    def get_name_tried(self, phone_number: str) -> bool:
        data = self.load_conversation_file(phone_number)
        if not data:
            return False
        return data.get("name_tried", False)

    def set_name_tried(self, phone_number: str, tried: bool) -> None:
        data = self.load_conversation_file(phone_number)
        data["name_tried"] = tried
        self.save_conversation_file(phone_number, data)

    def format_order_summary(self, order_summary: str) -> List[Dict[str, Any]]:
        return json.loads(order_summary)

    def set_order_confirmed(self, phone_number: str, order_summary: str, confirmed: bool) -> None:
        data = self.load_conversation_file(phone_number)
        data["order_confirmed"] = {
            "confirmed": confirmed,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "order_summary": self.format_order_summary(order_summary)
        }
        self.save_conversation_file(phone_number, data)

    def get_conversation_history(self, phone_number: str, max_age_seconds: int = 84600) -> List[Dict[str, Any]]:
        data = self.load_conversation_file(phone_number)
        if not data:
            return []
        last_updated = data.get("last_updated", 0)
        if time.time() - last_updated > max_age_seconds:
            # ⚠️ Conversación vieja: limpiamos historial pero mantenemos el resto
            data["history"] = []
            data["last_updated"] = time.time()
            self.save_conversation_file(phone_number, data)
            self.log.warning(f"⚠️ Conversación vieja limpiada para {phone_number}")
            return []
        return data.get("history", [])

    def add_to_conversation_history(self, phone_number: str, role: str, content: str) -> List[Dict[str, Any]]:
        data = self.load_conversation_file(phone_number)
        if not data:
            data = {
                "phone_number": phone_number,
                "name": "",
                "last_updated": time.time(),
                "history": []
            }
        history = data.get("history", [])
        history.append({
            "role": role,
            "content": content,
            "timestamp": time.time()
        })
        # Limitar historial
        if len(history) > 20:
            history = history[-20:]
        data["history"] = history
        data["last_updated"] = time.time()
        self.save_conversation_file(phone_number, data)
        return history

    def set_customer_name(self, phone_number: str, name: str) -> None:
        data = self.load_conversation_file(phone_number)
        data["name"] = name
        data["last_updated"] = time.time()
        self.save_conversation_file(phone_number, data)
        self.log.info(f"👤 Nombre actualizado para {phone_number}: {name}")

# Create a singleton instance
conversation_service = ConversationService()
