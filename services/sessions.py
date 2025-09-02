# services/sessions.py
import os
import json
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

DATA_ROOT = Path(__file__).resolve().parent.parent / "data" / "sessions"
DATA_ROOT.mkdir(parents=True, exist_ok=True)

SESSION_TTL_HOURS = 24

def _now():
    return datetime.now(timezone.utc)

def _session_path(session_id: str) -> Path:
    return DATA_ROOT / session_id

def _convo_file(session_id: str) -> Path:
    return _session_path(session_id) / "convo.json"

def start_or_refresh_session(phone: str) -> str:
    """
    Crea o renueva una sesión (24h) asociada al número de teléfono.
    Devuelve session_id (string).
    """
    # Usamos el teléfono como clave base
    session_id = f"{phone}"
    path = _session_path(session_id)
    path.mkdir(parents=True, exist_ok=True)

    # Creamos/renovamos metadata
    meta_file = path / "meta.json"
    now = _now()
    expires = now + timedelta(hours=SESSION_TTL_HOURS)
    metadata = {"phone": phone, "started": now.isoformat(), "expires": expires.isoformat()}
    with open(meta_file, "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2, ensure_ascii=False)

    # Asegurar que convo.json exista
    convo_file = _convo_file(session_id)
    if not convo_file.exists():
        with open(convo_file, "w", encoding="utf-8") as f:
            json.dump([], f)

    return session_id

def append_convo_message(session_id: str, role: str, text: str):
    """
    Agrega un mensaje al convo.json dentro de la sesión.
    """
    convo_file = _convo_file(session_id)
    if not convo_file.exists():
        raise FileNotFoundError(f"Sesión {session_id} no encontrada")

    with open(convo_file, "r", encoding="utf-8") as f:
        convo = json.load(f)

    convo.append({
        "role": role,
        "text": text,
        "ts": _now().isoformat()
    })

    with open(convo_file, "w", encoding="utf-8") as f:
        json.dump(convo, f, indent=2, ensure_ascii=False)
