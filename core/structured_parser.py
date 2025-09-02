# core/structured_parser.py
import copy
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
    # Si el modelo “entendió” metros en vez de cm (1.60–2.60), convierto a cm
    t = data.antropometria.talla_cm
    if t and 2.2 < float(t) < 2.6:
        data.antropometria.talla_cm = round(float(t) * 100)

    # Recalcular IMC si tengo peso+talla
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

def llm_update_state(user_text: str, current_state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Llama a responses.parse con Pydantic y devuelve el nuevo estado mergeado
    (sin pisar con null/empty).
    """
    # 1) Pedimos structured output validado
    out: FichaPreanestesia = client.responses.parse(
        model=OPENAI_MODEL,
        input=user_text,
        response_format=FichaPreanestesia,  # <- valida y devuelve objeto Pydantic
    )

    # 2) Normalizaciones mínimas (m→cm, IMC)
    out = _normalize_units(out)

    # 3) Merge no destructivo con el estado previo
    prev = copy.deepcopy(current_state) if current_state else {}
    merged = _deep_merge_non_null(prev, out.model_dump())
    return merged
