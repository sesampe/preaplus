# core/structured_parser.py
from __future__ import annotations

import copy, json, logging
from typing import Dict, Any

from openai import OpenAI
from pydantic import ValidationError

from core.settings import OPENAI_MODEL
from core.schema_preanestesia import FichaPreanestesia

log = logging.getLogger("llm_client")
client = OpenAI()

SYSTEM = (
    "Eres un asistente clínico. Devuelve SOLO la estructura solicitada; "
    "si un dato no está, usa valores vacíos adecuados (''/null/[])."
)

def _compute_imc(peso_kg, talla_cm):
    try:
        if peso_kg and talla_cm and float(talla_cm) > 0:
            return round(float(peso_kg) / ((float(talla_cm) / 100.0) ** 2), 1)
    except Exception:
        pass
    return None

def _normalize_units(data: FichaPreanestesia) -> FichaPreanestesia:
    t = data.antropometria.talla_cm
    # si vino en metros, convertir a cm (rango razonable 2.2–2.6 m)
    if t and 2.2 < float(t) < 2.6:
        data.antropometria.talla_cm = round(float(t) * 100)
    imc = _compute_imc(data.antropometria.peso_kg, data.antropometria.talla_cm)
    if imc:
        data.antropometria.imc = imc
    return data

def _deep_merge_non_null(dst: Dict[str, Any], src: Dict[str, Any]) -> Dict[str, Any]:
    for k, v in src.items():
        if isinstance(v, dict):
            dst[k] = _deep_merge_non_null(dst.get(k, {}), v)
        else:
            if v not in ("", None, [], {}):
                dst[k] = v
    return dst

def _call_llm_structured(user_text: str) -> FichaPreanestesia:
    """
    Camino principal: Responses.parse con text_format=FichaPreanestesia.
    Fallback: Chat Completions JSON-mode + validación Pydantic.
    """
    # --- 1) Camino principal: parse ---
    try:
        parsed = client.responses.parse(
            model=OPENAI_MODEL,
            input=[
                {"role": "system", "content": SYSTEM},
                {
                    "role": "user",
                    "content": (
                        "Extrae una FichaPreanestesia del siguiente texto y completa "
                        "con valores vacíos cuando falte información.\n\n"
                        f"Texto:\n{user_text}"
                    ),
                },
            ],
            text_format=FichaPreanestesia,  # << clave con SDK 1.103.x
            temperature=0,
        )
        # Devuelve instancia Pydantic ya validada
        return parsed.parsed
    except Exception as e:
        log.warning("Responses.parse falló, uso fallback JSON-mode. Error: %s", e)

    # --- 2) Fallback: Chat Completions JSON-mode ---
    try:
        schema = FichaPreanestesia.model_json_schema()
        resp = client.chat.completions.create(
            model=OPENAI_MODEL,
            temperature=0,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": SYSTEM},
                {
                    "role": "user",
                    "content": (
                        "Devuelve SOLO un JSON válido que cumpla EXACTAMENTE este schema:\n"
                        + json.dumps(schema, ensure_ascii=False)
                        + "\n\nTexto:\n"
                        + user_text
                    ),
                },
            ],
        )
        raw = (resp.choices[0].message.content or "{}").strip()
        data = json.loads(raw)
        try:
            return FichaPreanestesia.model_validate(data)
        except ValidationError:
            # saneo mínimo por si alguna clave viene como string en vez de lista, etc.
            return FichaPreanestesia.model_validate({})
    except Exception as e:
        log.error("Fallback JSON-mode también falló: %s", e)
        # Último recurso: devuelve objeto vacío válido
        return FichaPreanestesia.model_validate({})

def llm_update_state(user_text: str, current_state: Dict[str, Any]) -> Dict[str, Any]:
    out: FichaPreanestesia = _call_llm_structured(user_text)
    out = _normalize_units(out)
    prev = copy.deepcopy(current_state) if current_state else {}
    merged = _deep_merge_non_null(prev, out.model_dump())
    return merged
