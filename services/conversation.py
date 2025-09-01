# services/conversation.py
import os
import json
import asyncio
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Callable, Awaitable

# -------------------------------------------------------------------
# Configuración de almacenamiento
# -------------------------------------------------------------------
CONVERSATIONS_DIR = os.path.join("data", "conversations")
os.makedirs(CONVERSATIONS_DIR, exist_ok=True)

TTL_HOURS = 24  # sesiones efímeras de 24h

# -------------------------------------------------------------------
# Campos del formulario (state machine liviana)
# Podés modificar el orden, textos y validaciones a gusto.
# -------------------------------------------------------------------
def _validate_non_empty(value: str) -> bool:
    return bool(value.strip())

def _validate_si_no(value: str) -> bool:
    v = value.strip().lower()
    return v in {"si", "sí", "no"}

def _validate_dni(value: str) -> bool:
    v = value.replace(".", "").replace(" ", "")
    return v.isdigit() and 6 <= len(v) <= 10

def _validate_fecha_ddmmyyyy(value: str) -> bool:
    try:
        datetime.strptime(value.strip(), "%d/%m/%Y")
        return True
    except Exception:
        return False

FORM_FIELDS = [
    {
        "key": "nombre",
        "prompt": "¿Cuál es tu *nombre*?",
        "hint": None,
        "validate": _validate_non_empty,
        "error": "Por favor, ingresá un nombre válido."
    },
    {
        "key": "apellido",
        "prompt": "¿Y tu *apellido*?",
        "hint": None,
        "validate": _validate_non_empty,
        "error": "Por favor, ingresá un apellido válido."
    },
    {
        "key": "dni",
        "prompt": "Decime tu *DNI* (solo números).",
        "hint": "Ej: 12345678",
        "validate": _validate_dni,
        "error": "El DNI parece inválido. Probá solo con números, sin puntos."
    },
    {
        "key": "fecha_nacimiento",
        "prompt": "¿Tu *fecha de nacimiento*?",
        "hint": "Formato: DD/MM/AAAA",
        "validate": _validate_fecha_ddmmyyyy,
        "error": "Formato inválido. Usá DD/MM/AAAA (ej: 09/04/1990)."
    },
    {
        "key": "alergias",
        "prompt": "¿Tenés *alergias*? (si / no). Si tenés, podés detallar.",
        "hint": None,
        "validate": _validate_non_empty,  # permitimos texto libre
        "error": "Indicá si/no o describí brevemente."
    },
    {
        "key": "medicacion",
        "prompt": "¿Estás tomando *medicación actual*? (si / no). Si sí, ¿cuál?",
        "hint": None,
        "validate": _validate_non_empty,
        "error": "Indicá si/no o describí brevemente."
    },
    {
        "key": "antecedentes",
        "prompt": "¿Tenés *antecedentes médicos o quirúrgicos* relevantes?",
        "hint": "Podés responder con una breve lista o 'no'.",
        "validate": _validate_non_empty,
        "error": "Contame brevemente (o indicá 'no')."
    },
    {
        "key": "motivo",
        "prompt": "¿Cuál es el *motivo de la consulta* hoy?",
        "hint": None,
        "validate": _validate_non_empty,
        "error": "Necesito una breve descripción del motivo."
    },
]

# -------------------------------------------------------------------
# Utilidades
# -------------------------------------------------------------------
def _now_iso() -> str:
    return datetime.utcnow().isoformat()

def _expires_at_iso(hours: int = TTL_HOURS) -> str:
    return (datetime.utcnow() + timedelta(hours=hours)).isoformat()

def _is_expired(iso_str: str) -> bool:
    try:
        return datetime.utcnow() > datetime.fromisoformat(iso_str)
    except Exception:
        return True

def _filepath_for(user_id: str) -> str:
    safe = "".join(c for c in user_id if c.isalnum() or c in ("+", "-", "_", "@"))
    return os.path.join(CONVERSATIONS_DIR, f"{safe}.json")

def _load_session(user_id: str) -> Dict[str, Any]:
    fp = _filepath_for(user_id)
    if os.path.exists(fp):
        with open(fp, "r", encoding="utf-8") as f:
            return json.load(f)
    return {
        "user_id": user_id,
        "created_at": _now_iso(),
        "expires_at": _expires_at_iso(),
        "history": [],
        "form": {
            "index": 0,           # índice del campo actual a preguntar
            "data": {},           # valores recolectados
            "completed": False,   # bandera de finalización
        },
    }

def _save_session(user_id: str, data: Dict[str, Any]) -> None:
    fp = _filepath_for(user_id)
    with open(fp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def _append_history(sess: Dict[str, Any], role: str, content: str) -> None:
    sess["history"].append({
        "role": role,
        "content": content,
        "timestamp": _now_iso()
    })

def _format_prompt_for_llm(sess: Dict[str, Any]) -> str:
    """Prompt compacto para LLM con datos del formulario + último mensaje."""
    data = sess["form"]["data"]
    collected_lines = [f"- {k}: {v}" for k, v in data.items()]
    collected_str = "\n".join(collected_lines) if collected_lines else "(vacío)"
    return (
        "Contexto: asistente para preanestesia/triage con tono claro y empático.\n"
        "Datos recolectados hasta ahora:\n"
        f"{collected_str}\n\n"
        "Objetivo: responder de forma breve (máx 3 oraciones), confirmar lo entendido, "
        "y si falta información, pedirla de manera concreta.\n"
    )

def _build_field_prompt(field_cfg: Dict[str, Any]) -> str:
    prompt = field_cfg["prompt"]
    if field_cfg.get("hint"):
        prompt += f"\n({field_cfg['hint']})"
    return prompt

# -------------------------------------------------------------------
# Clase principal
# -------------------------------------------------------------------
# Firma esperada para el LLM: async def get_llm_response(prompt: str, history: List[Dict[str, str]]) -> str
LLMFunc = Optional[Callable[[str, List[Dict[str, str]]], Awaitable[str]]]

class ConversationEngine:
    """
    Orquesta el flujo de conversación:
    - TTL 24h por user_id (teléfono)
    - state machine liviana para guía de preguntas
    - historial persistente (JSON) => se envía al LLM
    - comandos: reset/reiniciar, json, final
    - integración con wa_client (send_message) y logger (log)
    """

    def __init__(self, wa_client: Any, get_llm_response: LLMFunc = None, logger: Optional[Any] = None):
        self.wa_client = wa_client
        self.get_llm_response = get_llm_response
        # logger debe exponer un método .info/.error o .log(str)
        self.logger = logger

    # ------------------------- Logging helper -------------------------
    def log(self, msg: str) -> None:
        try:
            if hasattr(self.logger, "info"):
                self.logger.info(msg)
            elif hasattr(self.logger, "log"):
                self.logger.log(msg)
        except Exception:
            pass

    # ---------------------- Session (load/save) -----------------------
    def _get_session(self, user_id: str) -> Dict[str, Any]:
        sess = _load_session(user_id)
        if _is_expired(sess.get("expires_at", "")):
            # Reset de sesión expirada (no traemos memoria histórica vieja)
            sess = {
                "user_id": user_id,
                "created_at": _now_iso(),
                "expires_at": _expires_at_iso(),
                "history": [],
                "form": {"index": 0, "data": {}, "completed": False},
            }
            _save_session(user_id, sess)
        return sess

    def _save_session(self, user_id: str, sess: Dict[str, Any]) -> None:
        _save_session(user_id, sess)

    # ---------------------- Commands handlers ------------------------
    async def _cmd_reset(self, user_id: str) -> None:
        sess = {
            "user_id": user_id,
            "created_at": _now_iso(),
            "expires_at": _expires_at_iso(),
            "history": [],
            "form": {"index": 0, "data": {}, "completed": False},
        }
        _save_session(user_id, sess)
        await self._send(user_id, "Listo ✅ Reiniciamos la sesión. Empecemos de nuevo.")
        await self._ask_next(user_id, sess)

    async def _cmd_json(self, user_id: str, sess: Dict[str, Any]) -> None:
        data = sess["form"]["data"]
        missing = [f["key"] for f in FORM_FIELDS if f["key"] not in data or not str(data[f["key"]]).strip()]
        pretty = json.dumps({"user_id": user_id, "datos": data, "completo": len(missing) == 0}, ensure_ascii=False, indent=2)
        await self._send(user_id, f"```json\n{pretty}\n```")
        if missing:
            # Ayuda a continuar el flujo
            await self._send(user_id, f"Falta completar: {', '.join(missing)}. Sigamos…")
            await self._ask_next(user_id, sess)

    async def _cmd_final(self, user_id: str, sess: Dict[str, Any]) -> None:
        # Marca como completo y devuelve el JSON final
        sess["form"]["completed"] = True
        self._save_session(user_id, sess)
        await self._send(user_id, "¡Perfecto! Marcamos el formulario como completo ✅")
        await self._cmd_json(user_id, sess)

    # --------------------------- I/O ---------------------------------
    async def _send(self, user_id: str, text: str) -> None:
        # Enviar por WhatsApp
        try:
            self.wa_client.send_message(user_id, text)
        except Exception as e:
            self.log(f"[WA ERROR] {e}")
        # Log bonito
        try:
            self.log(f"📤 Enviando respuesta a {user_id}: {text[:2000]}")
        except Exception:
            pass

    # ------------------------- Flow helpers --------------------------
    async def _ask_next(self, user_id: str, sess: Dict[str, Any]) -> None:
        """Pregunta el próximo campo o cierra si ya está completo."""
        idx = sess["form"]["index"]
        data = sess["form"]["data"]

        if idx >= len(FORM_FIELDS):
            sess["form"]["completed"] = True
            self._save_session(user_id, sess)
            await self._send(user_id, "🎉 ¡Listo! Ya completamos todos los datos.")
            await self._cmd_json(user_id, sess)
            return

        field_cfg = FORM_FIELDS[idx]
        prompt = _build_field_prompt(field_cfg)
        await self._send(user_id, prompt)

    def _capture_answer(self, sess: Dict[str, Any], text: str) -> Optional[str]:
        """
        Intenta validar y guardar la respuesta para el campo actual.
        Devuelve None si OK; o el string de error si falla la validación.
        """
        idx = sess["form"]["index"]
        if idx >= len(FORM_FIELDS):
            return None

        field_cfg = FORM_FIELDS[idx]
        val = text.strip()

        try:
            is_valid = field_cfg["validate"](val)
        except Exception:
            is_valid = False

        if not is_valid:
            return field_cfg["error"]

        # Persistimos la respuesta válida
        sess["form"]["data"][field_cfg["key"]] = val
        sess["form"]["index"] = idx + 1
        return None

    # ---------------------- LLM interaction --------------------------
    async def _maybe_llm_reply(self, user_id: str, sess: Dict[str, Any]) -> None:
        """
        Si se inyectó get_llm_response, generamos una respuesta corta
        de acompañamiento basada en historial + datos ya recolectados.
        """
        if not self.get_llm_response:
            return
        try:
            prompt = _format_prompt_for_llm(sess)
            # Para el LLM, usamos solo role/content del historial.
            history_min = [{"role": h["role"], "content": h["content"]} for h in sess["history"][-20:]]
            reply = await self.get_llm_response(prompt, history_min)
            if reply and reply.strip():
                await self._send(user_id, reply.strip())
        except Exception as e:
            self.log(f"[LLM ERROR] {e}")

    # ---------------------- Public entrypoint ------------------------
    async def handle_message(self, user_id: str, text: str) -> None:
        """
        Punto de entrada principal. Llamar desde tu route/handler de WhatsApp:
            await conv_engine.handle_message(sender_phone, incoming_text)
        """
        incoming = (text or "").strip()
        self.log(f"📨 Mensaje de {user_id}: {incoming}")

        sess = self._get_session(user_id)

        # Renovamos TTL en cada mensaje
        sess["expires_at"] = _expires_at_iso()
        _append_history(sess, "user", incoming)
        self._save_session(user_id, sess)

        # -------------------- Comandos --------------------
        low = incoming.lower()
        if low in {"reset", "reiniciar"}:
            await self._cmd_reset(user_id)
            return
        if low in {"json", "final"}:
            if low == "json":
                await self._cmd_json(user_id, sess)
            else:
                await self._cmd_final(user_id, sess)
            return

        # -------------------- Flujo del formulario --------------------
        if not sess["form"]["completed"]:
            err = self._capture_answer(sess, incoming)
            if err:
                self._save_session(user_id, sess)
                await self._send(user_id, f"⚠️ {err}")
                # Re-preguntamos el mismo campo
                idx = sess["form"]["index"]
                field_cfg = FORM_FIELDS[idx]
                await self._send(user_id, _build_field_prompt(field_cfg))
                return

            # Guardado OK → pasamos al siguiente campo o cerramos
            self._save_session(user_id, sess)
            await self._ask_next(user_id, sess)

            # Respuesta breve del LLM (si está inyectado), para acompañar el flujo
            await self._maybe_llm_reply(user_id, sess)
            return

        # -------------------- Si el formulario ya estaba completo --------------------
        # Seguimos conversando con LLM con el historial + datos; útil para dudas post-cierre.
        await self._maybe_llm_reply(user_id, sess)

# -------------------------------------------------------------------
# Ejemplo de integración (opcional):
# 
# from services.conversation import ConversationEngine
#
# class MyRoutes:
#     def __init__(self, wa_client, logger, get_llm_response):
#         self.conv = ConversationEngine(
#             wa_client=wa_client,
#             get_llm_response=get_llm_response,  # async (prompt, history) -> str
#             logger=logger,
#         )
#
#     async def on_incoming(self, sender_phone: str, text: str):
#         await self.conv.handle_message(sender_phone, text)
#
# Donde:
# - wa_client.send_message(to: str, text: str) envía por WhatsApp
# - logger.info(str) registra
# - get_llm_response es una corrutina async que devuelve un string
# -------------------------------------------------------------------
