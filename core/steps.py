# steps.py
from typing import Dict, Any, List, Tuple, Optional
from datetime import date
import json

from models.schemas import ConversationState, FichaPreanestesia, AlergiaMedicacion, Alergias, AlergiaItem, MedicacionItem, Antecedentes, Cardio, Respiratorio, Endocrino, Renal, Neuro, Complementarios, Labs, ImagenItem
from services.validators import (
    parse_dni, parse_fecha, edad_from_fecha_nacimiento,
    parse_peso_kg, parse_talla_cm, calc_imc,
    parse_afiliado, parse_tabaco, parse_alcohol, parse_via_aerea,
    hb_en_rango, plaquetas_en_rango, creatinina_en_rango, inr_en_rango
)
from llm_client import llm_client

# ===== Definición de módulos =====

MODULES: List[Dict[str, Any]] = [
    {"name": "DNI", "use_llm": False, "required": ["ficha.dni"]},
    {"name": "DATOS", "use_llm": False, "required": ["ficha.datos.nombre_completo", "ficha.datos.fecha_nacimiento", "ficha.datos.edad", "ficha.datos.fecha_evaluacion"]},
    {"name": "ANTROPOMETRIA", "use_llm": False, "required": ["ficha.antropometria.peso_kg", "ficha.antropometria.talla_cm", "ficha.antropometria.imc"]},
    {"name": "COBERTURA", "use_llm": False, "required": ["ficha.cobertura.obra_social", "ficha.cobertura.afiliado", "ficha.cobertura.motivo_cirugia"]},
    {"name": "ALERGIA_MEDICACION", "use_llm": True, "required": ["ficha.alergia_medicacion"]},
    {"name": "ANTECEDENTES", "use_llm": True, "required": ["ficha.antecedentes"]},
    {"name": "COMPLEMENTARIOS", "use_llm": True, "required": []},  # nada estrictamente obligatorio
    {"name": "SUSTANCIAS", "use_llm": False, "required": []},
    {"name": "VIA_AEREA", "use_llm": False, "required": []},
]

# ===== Util =====

def _set(d: Dict, path: str, value: Any):
    parts = path.split(".")
    cur = d
    for p in parts[:-1]:
        if p not in cur or not isinstance(cur[p], dict):
            cur[p] = {}
        cur = cur[p]
    cur[parts[-1]] = value

def _get(d: Dict, path: str) -> Any:
    parts = path.split(".")
    cur = d
    for p in parts:
        if not isinstance(cur, dict) or p not in cur:
            return None
        cur = cur[p]
    return cur

def _missing_required(state: ConversationState, module_idx: int) -> List[str]:
    must = MODULES[module_idx]["required"]
    dump = json.loads(state.ficha.model_dump_json())
    missing = []
    for path in must:
        if _get(dump, path) in (None, "", []):
            missing.append(path)
    return missing

def _now_date() -> date:
    return date.today()

# ===== Parsers locales por módulo =====

def fill_from_text_modular(state: ConversationState, module_idx: int, text: str) -> Dict[str, Any]:
    """Devuelve un patch dict (serializable) con lo que pudo extraer localmente."""
    patch: Dict[str, Any] = {}
    name = MODULES[module_idx]["name"]

    if name == "DNI":
        dni = parse_dni(text)
        if dni:
            _set(patch, "ficha.dni", dni)

    elif name == "DATOS":
        # nombre heurístico: primeras 3 palabras con mayúscula inicial
        nombre = None
        tokens = [t for t in (text or "").strip().split() if t.istitle()]
        if len(tokens) >= 2:
            nombre = " ".join(tokens[:3])[:80]
        fnac = parse_fecha(text)
        edad = edad_from_fecha_nacimiento(fnac) if fnac else None
        if nombre:
            _set(patch, "ficha.datos.nombre_completo", nombre)
        if fnac:
            _set(patch, "ficha.datos.fecha_nacimiento", fnac.isoformat())
        if edad is not None:
            _set(patch, "ficha.datos.edad", edad)
        _set(patch, "ficha.datos.fecha_evaluacion", _now_date().isoformat())

    elif name == "ANTROPOMETRIA":
        peso = parse_peso_kg(text)
        talla = parse_talla_cm(text)
        if peso is not None:
            _set(patch, "ficha.antropometria.peso_kg", peso)
        if talla is not None:
            _set(patch, "ficha.antropometria.talla_cm", talla)
        imc = calc_imc(peso if peso is not None else state.ficha.antropometria.peso_kg,
                       talla if talla is not None else state.ficha.antropometria.talla_cm)
        if imc is not None:
            _set(patch, "ficha.antropometria.imc", imc)

    elif name == "COBERTURA":
        # libre para obra social y motivo; afiliado con 4+ alfanum
        afiliado = parse_afiliado(text)
        if afiliado:
            _set(patch, "ficha.cobertura.afiliado", afiliado)
        # heurística para OS: toma todo el texto si no hay nada cargado aún
        if text and len(text.strip()) >= 3 and not state.ficha.cobertura.obra_social:
            _set(patch, "ficha.cobertura.obra_social", text.strip()[:80])
        if text and len(text.strip()) >= 3 and not state.ficha.cobertura.motivo_cirugia:
            _set(patch, "ficha.cobertura.motivo_cirugia", text.strip()[:160])

    elif name == "SUSTANCIAS":
        fuma, packs, ap = parse_tabaco(text)
        bebe, tragos = parse_alcohol(text)
        if fuma is not None or packs is not None or ap is not None:
            _set(patch, "ficha.sustancias.tabaco.consume", fuma)
            if packs is not None:
                _set(patch, "ficha.sustancias.tabaco.paquetes_dia", packs)
            if ap is not None:
                _set(patch, "ficha.sustancias.tabaco.anos_paquete", ap)
        if bebe is not None or tragos is not None:
            _set(patch, "ficha.sustancias.alcohol.consume", bebe)
            if tragos is not None:
                _set(patch, "ficha.sustancias.alcohol.tragos_semana", tragos)

    elif name == "VIA_AEREA":
        flags = parse_via_aerea(text)
        for k, v in flags.items():
            if v is not None:
                _set(patch, f"ficha.via_aerea.{k}", v)

    return patch

# ===== LLM prompts chicos por módulo =====

def _prompt_alergia_medicacion(text: str) -> str:
    return (
        'Extraé alergias y medicación habitual de este texto en JSON. '
        'Esquema: {"alergias":{"tiene_alergias":bool,"detalle":[{"sustancia":str,"reaccion":str?}]},'
        '"medicacion_habitual":[{"droga":str,"dosis":str?,"frecuencia":str?}]}. '
        'Responde solo JSON, sin comentarios.\n'
        f'TEXTO:\n{text}'
    )

def _prompt_por_sistema(text: str, sistema: str, esquema: str) -> str:
    return (
        f'Busca SOLO antecedentes del sistema {sistema}. '
        f'Esquema: {esquema} Responde JSON. Sin comentarios.\n'
        f'TEXTO:\n{text}'
    )

def _prompt_complementarios(text: str) -> str:
    return (
        'Parseá laboratorio/estudios a: '
        '{"labs":{"hb":float?,"plaquetas":int?,"creatinina":float?,"inr":float?,"otros":[{"nombre":str,"valor":str}]},'
        '"imagenes":[{"estudio":str,"hallazgo":str}]}. '
        'Responde solo JSON.\n'
        f'TEXTO:\n{text}'
    )

def _safe_parse_json(s: str) -> Optional[dict]:
    try:
        return json.loads(s)
    except Exception:
        return None

def llm_parse_modular(text: str, module_idx: int) -> Dict[str, Any]:
    name = MODULES[module_idx]["name"]
    patch: Dict[str, Any] = {}

    if name == "ALERGIA_MEDICACION":
        out = llm_client.call_llm_simple(_prompt_alergia_medicacion(text), max_tokens=200)
        data = _safe_parse_json(out) or {}
        # Validación simple
        alergias = data.get("alergias") or {}
        tiene = bool(alergias.get("tiene_alergias"))
        detalle = alergias.get("detalle") or []
        if not tiene:
            detalle = []
        am = {
            "alergias": {"tiene_alergias": tiene, "detalle": detalle},
            "medicacion_habitual": data.get("medicacion_habitual") or []
        }
        _set(patch, "ficha.alergia_medicacion", am)

    elif name == "ANTECEDENTES":
        # Iteramos por sistemas con prompts chicos
        cardio_esquema = '{"cardio":{"hta":bool,"iam":bool,"falla_card":bool,"otros":[str]}}'
        resp_esquema = '{"respiratorio":{"epoc":bool,"asma":bool,"apnea_sueño":bool,"otros":[str]}}'
        endo_esquema = '{"endocrino":{"dm":bool,"hipotiroidismo":bool,"hipertiroidismo":bool,"otros":[str]}}'
        renal_esquema = '{"renal":{"irc":bool,"dialisis":bool,"otros":[str]}}'
        neuro_esquema = '{"neuro":{"acv":bool,"convulsiones":bool,"otros":[str]}}'

        acc: Dict[str, Any] = {}
        for sis, esquema in [
            ("cardiovascular", cardio_esquema),
            ("respiratorio", resp_esquema),
            ("endócrino", endo_esquema),
            ("renal", renal_esquema),
            ("neurológico", neuro_esquema),
        ]:
            out = llm_client.call_llm_simple(_prompt_por_sistema(text, sis, esquema), max_tokens=200)
            data = _safe_parse_json(out) or {}
            acc.update(data)

        _set(patch, "ficha.antecedentes", acc)

    elif name == "COMPLEMENTARIOS":
        out = llm_client.call_llm_simple(_prompt_complementarios(text), max_tokens=220)
        data = _safe_parse_json(out) or {}
        labs = data.get("labs") or {}
        # rangos básicos si hay números
        if not hb_en_rango(labs.get("hb")):
            labs["hb"] = None
        if not plaquetas_en_rango(labs.get("plaquetas")):
            labs["plaquetas"] = None
        if not creatinina_en_rango(labs.get("creatinina")):
            labs["creatinina"] = None
        if not inr_en_rango(labs.get("inr")):
            labs["inr"] = None
        comp = {
            "labs": labs,
            "imagenes": data.get("imagenes") or []
        }
        _set(patch, "ficha.complementarios", comp)

    return patch

# ===== Avance y mensajes =====

def advance_module(state: ConversationState) -> Tuple[Optional[int], Optional[str]]:
    """Devuelve (next_idx, next_prompt) o (None, None) si terminó."""
    for i in range(state.module_idx, len(MODULES)):
        missing = _missing_required(state, i)
        if missing:
            return i, prompt_for_module(i)
        # incluso si no hay missing, igual pedimos input del módulo para confirmación breve
        if i == state.module_idx:
            return i, prompt_for_module(i)
    return None, None

def prompt_for_module(module_idx: int) -> str:
    name = MODULES[module_idx]["name"]
    prompts = {
        "DNI": "Decime tu DNI (solo números).",
        "DATOS": "Nombre y apellido, y tu fecha de nacimiento (dd/mm/aaaa).",
        "ANTROPOMETRIA": "Decime peso (kg) y talla (cm o en metros).",
        "COBERTURA": "¿Cuál es tu obra social y n.º de afiliado? ¿Motivo de la cirugía?",
        "ALERGIA_MEDICACION": "Contame alergias (si tenés) y medicación habitual (droga/dosis/frecuencia).",
        "ANTECEDENTES": "Antecedentes por sistemas (cardio, respiratorio, endócrino, renal, neuro...).",
        "COMPLEMENTARIOS": "Laboratorio e imágenes relevantes (Hb, plaquetas, creatinina, INR, estudios e informe).",
        "SUSTANCIAS": "Tabaco (paquetes/día y años), alcohol (tragos/semana) u otras sustancias.",
        "VIA_AEREA": "¿Alguna vez intubación difícil? ¿Piezas dentarias flojas o prótesis?",
    }
    return prompts.get(name, "Contame lo que corresponda para este bloque.")

def summarize_patch_for_confirmation(patch: Dict[str, Any], module_idx: int) -> str:
    name = MODULES[module_idx]["name"]
    try:
        if name == "DNI":
            return f"Anoté DNI: {patch['ficha']['dni']}"
        if name == "DATOS":
            d = patch["ficha"]["datos"]
            return f"Anoté: {d.get('nombre_completo')}, nac. {d.get('fecha_nacimiento')}, edad {d.get('edad')}"
        if name == "ANTROPOMETRIA":
            a = patch["ficha"]["antropometria"]
            return f"Anoté: peso {a.get('peso_kg')} kg, talla {a.get('talla_cm')} cm, IMC {a.get('imc')}"
        if name == "COBERTURA":
            c = patch["ficha"]["cobertura"]
            return f"Anoté: OS {c.get('obra_social')}, afiliado {c.get('afiliado')}, motivo {c.get('motivo_cirugia')}"
        if name == "ALERGIA_MEDICACION":
            return "Anoté alergias y medicación habitual."
        if name == "ANTECEDENTES":
            return "Anoté antecedentes por sistemas."
        if name == "COMPLEMENTARIOS":
            return "Anoté complementarios (labs/imagenes)."
        if name == "SUSTANCIAS":
            return "Anoté consumo de tabaco/alcohol/otras."
        if name == "VIA_AEREA":
            return "Anoté datos de vía aérea."
    except Exception:
        pass
    return "Anoté el bloque."

def merge_state(state: ConversationState, patch: Dict[str, Any]) -> ConversationState:
    """Merge shallow-recursive dict into Pydantic model."""
    # usamos dump->merge->load para simplicidad
    base = json.loads(state.ficha.model_dump_json())
    def rec_merge(dst, src):
        for k, v in src.items():
            if isinstance(v, dict) and isinstance(dst.get(k), dict):
                rec_merge(dst[k], v)
            else:
                dst[k] = v
    rec_merge(base, patch.get("ficha", {}))
    state.ficha = FichaPreanestesia(**base)
    return state
