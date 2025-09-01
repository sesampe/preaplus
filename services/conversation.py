import os
import re
import uuid
import json

from pathlib import Path
from datetime import datetime, timedelta, timezone

from typing import List, Dict, Any, Optional
from datetime import datetime

from core.settings import CONVERSATION_HISTORY_DIR, TAKEOVER_FILE
from core.logger import LoggerManager
from models.schemas import ConversationContext


################ AGREGADO ------------------------------------------
# conversation.py
import json
import re
import uuid
from pathlib import Path
from datetime import datetime, timedelta, timezone

DATA_DIR = Path("./data/sessions")
INDEX_PATH = DATA_DIR / "index.json"
SESSION_TTL_HOURS = 24

# --------------------------
# Utilidades básicas de disco
# --------------------------

def _now_utc():
    return datetime.now(timezone.utc)

def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat()

def _from_iso(s: str) -> datetime:
    return datetime.fromisoformat(s)

def ensure_dirs():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if not INDEX_PATH.exists():
        INDEX_PATH.write_text(json.dumps({}, ensure_ascii=False, indent=2))

def read_index() -> dict:
    ensure_dirs()
    try:
        return json.loads(INDEX_PATH.read_text() or "{}")
    except Exception:
        return {}

def write_index(idx: dict):
    ensure_dirs()
    INDEX_PATH.write_text(json.dumps(idx, ensure_ascii=False, indent=2))

def session_dir(session_id: str) -> Path:
    p = DATA_DIR / session_id
    p.mkdir(parents=True, exist_ok=True)
    return p

def read_json(path: Path, default):
    try:
        if path.exists():
            return json.loads(path.read_text() or json.dumps(default))
    except Exception:
        pass
    return default

def write_json(path: Path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2))

# --------------------------
# Normalización de DNI
# --------------------------

_DNI_RE = re.compile(r"[A-Za-z0-9]+")

def normalize_dni(raw: str) -> str:
    """
    - Quita espacios, puntos y símbolos
    - Mantiene alfanumérico
    - Uppercase (para RNxxxxx, etc.)
    - NO enmascara, NO hashea
    """
    if not raw:
        return ""
    parts = _DNI_RE.findall(str(raw))
    return "".join(parts).upper()

# --------------------------
# Sesiones por teléfono
# --------------------------

def _is_expired(expires_at_iso: str) -> bool:
    try:
        return _from_iso(expires_at_iso) <= _now_utc()
    except Exception:
        return True

def _new_expiry() -> str:
    return _iso(_now_utc() + timedelta(hours=SESSION_TTL_HOURS))

def get_or_create_session(telefono: str, dni_raw: str):
    """
    Regla:
    - Sin sesión vigente -> crear
    - Vigente y mismo dni -> reusar
    - Vigente y dni distinto -> crear nueva (otro paciente)
    """
    ensure_dirs()
    dni_norm = normalize_dni(dni_raw)
    idx = read_index()
    current = idx.get(telefono)

    # caso: no hay sesión o está vencida -> crear nueva
    if not current or _is_expired(current.get("expires_at", "")):
        sid = str(uuid.uuid4())
        idx[telefono] = {"session_id": sid, "expires_at": _new_expiry()}
        write_index(idx)
        _init_session_files(sid, telefono, dni_norm)
        return sid, dni_norm, "created"

    # hay sesión vigente -> revisar DNI
    sid = current["session_id"]
    p_path = session_dir(sid) / "patient.json"
    patient = read_json(p_path, {})
    dni_prev = patient.get("dni_normalizado")

    if dni_prev and dni_prev != dni_norm:
        # otro DNI: crear NUEVA sesión (otro paciente)
        sid = str(uuid.uuid4())
        idx[telefono] = {"session_id": sid, "expires_at": _new_expiry()}
        write_index(idx)
        _init_session_files(sid, telefono, dni_norm)
        return sid, dni_norm, "created_new_for_different_dni"

    # mismo DNI: reusar y extender ventana a 24h desde ahora
    idx[telefono]["expires_at"] = _new_expiry()
    write_index(idx)
    if not (session_dir(sid) / "patient.json").exists():
        _init_session_files(sid, telefono, dni_norm)
    else:
        _maybe_update_dni(sid, dni_norm)
    return sid, dni_norm, "reused"

def _init_session_files(session_id: str, telefono: str, dni_norm: str):
    sdir = session_dir(session_id)
    write_json(sdir / "convo.json", {"telefono": telefono, "created_at": _iso(_now_utc()), "messages": []})
    write_json(sdir / "patient.json", {"dni_normalizado": dni_norm, "respuestas": {}, "updated_at": _iso(_now_utc())})
    # output.json y PDF se generan al finalizar

def _maybe_update_dni(session_id: str, dni_norm: str):
    p_path = session_dir(session_id) / "patient.json"
    patient = read_json(p_path, {"respuestas": {}})
    if patient.get("dni_normalizado") != dni_norm:
        patient["dni_normalizado"] = dni_norm
        patient["updated_at"] = _iso(_now_utc())
        write_json(p_path, patient)

def append_message(session_id: str, role: str, text: str, meta: dict = None):
    c_path = session_dir(session_id) / "convo.json"
    convo = read_json(c_path, {"messages": []})
    convo.setdefault("messages", []).append({
        "ts": _iso(_now_utc()),
        "role": role,
        "text": text,
        "meta": meta or {}
    })
    write_json(c_path, convo)

def upsert_patient_answers(session_id: str, partial_answers: dict):
    p_path = session_dir(session_id) / "patient.json"
    patient = read_json(p_path, {"respuestas": {}})
    patient.setdefault("respuestas", {}).update(partial_answers or {})
    patient["updated_at"] = _iso(_now_utc())
    write_json(p_path, patient)
    return patient

# --------------------------
# Hooks: LLM y PDF
# --------------------------

def run_structured_output(session_id: str) -> dict:
    """
    Llama a TU LLM (Structured Output) con todo el historial (convo.json) y/o patient.json.
    Devuelve el JSON preformateado y lo persiste en output.json
    """
    sdir = session_dir(session_id)
    convo = read_json(sdir / "convo.json", {})
    patient = read_json(sdir / "patient.json", {})
    # TODO: reemplazar por tu llamada real a OpenAI / Llama / etc.
    output = {
        "version": 1,
        "generated_at": _iso(_now_utc()),
        "dni": patient.get("dni_normalizado"),
        "fields": patient.get("respuestas"),   # o lo que tu LLM estructure desde convo
        "trace": {"tokens": 0}
    }
    write_json(sdir / "output.json", output)
    return output

def generate_pdf_from_output(session_id: str, output: dict) -> str:
    """
    Genera el PDF con los datos de `output` y lo guarda como formulario.pdf.
    Retorna la ruta absoluta para servir/descargar.
    """
    sdir = session_dir(session_id)
    pdf_path = sdir / "formulario.pdf"
    # TODO: Integrar tu generador de PDF real: fill template con output["fields"]
    # Por ahora, placeholder: crea un PDF mínimo o deja un archivo marcador.
    pdf_path.write_bytes(b"%PDF-1.4\n%… PDF generado …\n%%EOF\n")
    return str(pdf_path)

# --------------------------
# Mantenimiento (opcional)
# --------------------------

def garbage_collect_sessions(delete_dirs: bool = False):
    """
    Limpia index.json de sesiones vencidas.
    Si delete_dirs=True, además borra carpetas de sesiones expiradas (cuidado en prod).
    """
    idx = read_index()
    changed = False
    for tel, rec in list(idx.items()):
        if _is_expired(rec.get("expires_at", "")):
            sid = rec.get("session_id")
            del idx[tel]
            changed = True
            if delete_dirs and sid:
                try:
                    sdir = session_dir(sid)
                    for p in sdir.glob("*"):
                        p.unlink(missing_ok=True)
                    sdir.rmdir()
                except Exception:
                    pass
    if changed:
        write_index(idx)

##################### FIN AGREGADO -------------------------------

class ConversationService:
    """Service for managing conversations, customer profiles, and interaction contexts.
    
    TODO: Database Integration
    When adding a database, consider:
    1. Create tables for:
       - conversations (id, phone_number, name, last_updated)
       - conversation_messages (id, conversation_id, role, content, timestamp)
       - customer_profiles (phone, name, created_at, last_interaction)
       - conversation_contexts (phone, last_intent, current_order_id, human_takeover)
    2. Use SQLAlchemy for ORM
    3. Move file-based storage to proper database tables
    4. Add database connection handling and connection pool
    """
    
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(ConversationService, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        """Initialize the Conversation service."""
        if self._initialized:
            return
            
        self.log = LoggerManager(name="conversation", level="INFO", log_to_file=False).get_logger()
        self._ensure_directories()
        self._takeover_expiration = 180  # seconds
        self._conversation_contexts: Dict[str, ConversationContext] = {}
        self._initialized = True
        
    def _ensure_directories(self) -> None:
        """Ensure required directories exist."""
        os.makedirs(CONVERSATION_HISTORY_DIR, exist_ok=True)
        
    def _sanitize_phone(self, phone: str) -> str:
        """Sanitize phone number for file operations."""
        return phone.replace(":", "_").replace("+", "").replace("whatsapp", "")
    
    def _get_conversation_filepath(self, phone_number: str) -> str:
        """Get the file path for a conversation."""
        filename = self._sanitize_phone(phone_number) + ".json"
        return os.path.join(CONVERSATION_HISTORY_DIR, filename)

    # -----------------------------
    # Conversation Context Management
    # -----------------------------
    def get_conversation_context(self, phone: str) -> ConversationContext:
        """Get or create conversation context for a customer.
        
        TODO: In database implementation, this would be a database query instead of in-memory dict.
        """
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
        """Update the conversation context for a customer.
        
        TODO: In database implementation, this would be a database update.
        """
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
        """Clear the conversation context for a customer.
        
        TODO: In database implementation, this would be a database delete.
        """
        if phone in self._conversation_contexts:
            del self._conversation_contexts[phone]

    # -----------------------------
    # Takeover Management
    # -----------------------------
    def load_takeover_status(self) -> Dict[str, dict]:
        """Load the current takeover status for all users.
        
        TODO: In database implementation, this would be a database query.
        """
        if os.path.exists(TAKEOVER_FILE):
            try:
                with open(TAKEOVER_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
            except json.JSONDecodeError:
                self.log.warning("⚠️ Error al leer el archivo de takeover, devolviendo vacío.")
                return {}
        return {}

    def save_takeover_status(self, status_dict: Dict[str, dict]) -> None:
        """Save the current takeover status.
        
        TODO: In database implementation, this would be a database update.
        """
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
        """Check if human takeover is active for a phone number."""
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
        """Set the human takeover status for a phone number."""
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
        """Load a conversation file for a phone number.
        
        TODO: In database implementation, this would be a database query joining
        conversations and conversation_messages tables.
        """
        filepath = self._get_conversation_filepath(phone_number)
        if os.path.exists(filepath):
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                self.log.error(f"❌ Error al leer conversación para {phone_number}: {e}")
        return {}

    def save_conversation_file(self, phone_number: str, data: dict) -> None:
        """Save a conversation file for a phone number.
        
        TODO: In database implementation, this would be database inserts/updates to
        conversations and conversation_messages tables.
        """
        filepath = self._get_conversation_filepath(phone_number)
        try:
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            self.log.info(f"💾 Conversación guardada para {phone_number}")
        except Exception as e:
            self.log.error(f"❌ Error al guardar conversación para {phone_number}: {e}")

    def get_name_from_conversation(self, phone_number: str) -> str:
        """Get the customer name from their conversation history.
        
        TODO: In database implementation, this would be a simple query to the
        customer_profiles table.
        """
        data = self.load_conversation_file(phone_number)
        if not data:
            return ""

        name = data.get("name", "")
        if not name:
            self.log.warning(f"⚠️ Nombre no encontrado en conversación para {phone_number}")
        return name
    
    def get_name_tried(self, phone_number: str) -> bool:
        """Check if the customer name has been tried to be extracted."""
        data = self.load_conversation_file(phone_number)
        if not data:
            return False

        name_tried = data.get("name_tried", False)

        return name_tried
    
    def set_name_tried(self, phone_number: str, tried: bool) -> None:
        """Set the customer name tried status."""
        data = self.load_conversation_file(phone_number)
        data["name_tried"] = tried
        self.save_conversation_file(phone_number, data)

    def format_order_summary(self, order_summary: str) -> List[Dict[str, Any]]:
        """Format the order summary."""
        return json.loads(order_summary)
    
    def set_order_confirmed(self, phone_number: str, order_summary: str, confirmed: bool) -> None:
        """Set the order confirmed status."""
        data = self.load_conversation_file(phone_number)

        data["order_confirmed"] = {
            "confirmed": confirmed,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "order_summary": self.format_order_summary(order_summary)
        }
        self.save_conversation_file(phone_number, data)

    def get_conversation_history(self, phone_number: str, max_age_seconds: int = 84600) -> List[Dict[str, Any]]:
        """Get the conversation history for a phone number.
        
        TODO: In database implementation, this would be a query to conversation_messages
        table with a timestamp filter.
        """
        data = self.load_conversation_file(phone_number)

        if not data:
            return []

        last_updated = data.get("last_updated", 0)
        if time.time() - last_updated > max_age_seconds:
            # ⚠️ Conversación vieja, limpiamos historial pero mantenemos el resto
            data["history"] = []
            data["last_updated"] = time.time()
            self.save_conversation_file(phone_number, data)
            self.log.warning(f"⚠️ Conversación vieja limpiada para {phone_number}")
            return []

        return data.get("history", [])

    def add_to_conversation_history(self, phone_number: str, role: str, content: str) -> List[Dict[str, Any]]:
        """Add a message to the conversation history.
        
        TODO: In database implementation, this would be an insert into the
        conversation_messages table.
        """
        data = self.load_conversation_file(phone_number)

        if not data:
            data = {
                "phone_number": phone_number,
                "name": "",  # Can be filled later
                "last_updated": time.time(),
                "history": []
            }

        history = data.get("history", [])
        history.append({
            "role": role,
            "content": content,
            "timestamp": time.time()
        })

        # Limit history
        if len(history) > 20:
            history = history[-20:]

        data["history"] = history
        data["last_updated"] = time.time()

        self.save_conversation_file(phone_number, data)
        return history

    def set_customer_name(self, phone_number: str, name: str) -> None:
        """Set the customer name in their conversation history.
        
        TODO: In database implementation, this would be an upsert to the
        customer_profiles table.
        """
        data = self.load_conversation_file(phone_number)
        data["name"] = name
        data["last_updated"] = time.time()
        self.save_conversation_file(phone_number, data)
        self.log.info(f"👤 Nombre actualizado para {phone_number}: {name}")

# Create a singleton instance
conversation_service = ConversationService()
