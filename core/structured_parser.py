# core/structured_parser.py
import copy, json
from typing import Dict, Any
from openai import OpenAI
from core.settings import OPENAI_MODEL
from core.schema_preanestesia import FichaPreanestesia

client = OpenAI()

def _compute_imc(peso_kg, talla_cm):
    try:
        if peso_kg and talla_cm and float(talla_cm) > 0:
            return round(float(peso_kg) / ((float(talla_cm)/100.0)**2), 1)
    except Exception:
        pass
    return None

def _normalize_units(data: FichaPreanestesia) -> FichaPreanestesia:
    t = data.antropometria.talla_cm
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
    Intenta usar responses.parse (SDK nuevo). Si no está, usa responses.create
    con json_schema y valida con Pydantic (SDK viejo).
    """
    try:
        # SDK nuevo: acepta response_format=FichaPreanestesia
        return client.responses.parse(
            model=OPENAI_MODEL,
            input=user_text,
            response_format=FichaPreanestesia,
        )
    except TypeError:
        # SDK viejo: generamos el schema y pedimos JSON validado
        schema = FichaPreanestesia.model_json_schema()
        resp = client.responses.create(
            model=OPENAI_MODEL,
            input=user_text,
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": "FichaPreanestesia",
                    "schema": schema,
                    "strict": True,
                },
            },
        )
        data = json.loads(resp.output_text)  # texto → dict
        return FichaPreanestesia.model_validate(data)

def llm_update_state(user_text: str, current_state: Dict[str, Any]) -> Dict[str, Any]:
    out: FichaPreanestesia = _call_llm_structured(user_text)
    out = _normalize_units(out)
    prev = copy.deepcopy(current_state) if current_state else {}
    merged = _deep_merge_non_null(prev, out.model_dump())
    return merged
