# steps.py
from typing import Dict, Any, List, Tuple, Optional
from datetime import date
import json
import re
from collections import defaultdict

from models.schemas import (
    ConversationState, FichaPreanestesia,
    AlergiaMedicacion, Alergias, AlergiaItem, MedicacionItem,
    Antecedentes, Cardio, Respiratorio, Endocrino, Renal, Neuro,
    Complementarios, Labs, ImagenItem
)
from services.validators import (
    parse_dni, parse_fecha, edad_from_fecha_nacimiento,
    parse_peso_kg, parse_talla_cm, calc_imc,
    parse_afiliado, parse_tabaco, parse_alcohol, parse_via_aerea,
    hb_en_rango, plaquetas_en_rango, creatinina_en_rango, inr_en_rango
)
from services.llm_client import llm_client

# ===== Config antibucle =====
MAX_RETRIES = 3  # intentos por módulo antes de dar fallback
# mapa global: id(state) -> { module_name: retries }
_RETRY_COUNTS: Dict[int, Dict[str, int]] = defaultdict(dict)

def _module_key(idx: int) -> str:
    return MODULES[idx]["name"]

def _inc_retry(state: ConversationState, module_idx: int) -> int:
    sid = id(state)
    k = _module_key(module_idx)
    cur = _RETRY_COUNTS[sid].get(k, 0) + 1
    _RETRY_COUNTS[sid][k] = cur
    return cur

def _reset_retry(state: ConversationState, module_idx: int):
    sid = id(state)
    k = _module_key(module_idx)
    if k in _RETRY_COUNTS[sid]:
        _RETRY_COUNTS[sid][k] = 0

def _retries(state: ConversationState, module_idx: int) -> int:
    sid = id(state)
    return int(_RETRY_COUNTS[sid].get(_module_key(module_idx), 0))

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
    """Devuelve un patch (con raíz 'ficha.*') con lo que pudo extraer localmente.
       Antibucle: si no se extrae nada, incrementa; si se llena algún requerido faltante, resetea."""
    patch: Dict[str, Any] = {}
    name = MODULES[module_idx]["name"]

    missing_before = set(_missing_required(state, module_idx))

    if name == "DNI":
        dni = parse_dni(text)
        if dni:
            _set(patch, "ficha.dni", dni)

    elif name == "DATOS":
        t = (text or "").strip()

        # nombre: acepta "me llamo/soy ..." o mayúsculas iniciales
        nombre = None
        m = re.search(r"(?:me llamo|soy)\s+([a-záéíóúñ]+(?:\s+[a-záéíóúñ]+){1,2})", t, re.I)
        if m:
            nombre = " ".join(w.capitalize() for w in m.group(1).split())[:80]
        else:
            tokens = [tok for tok in t.split() if tok[:1].isalpha() and tok.istitle()]
            if len(tokens) >= 2:
                nombre = " ".join(tokens[:3])[:80]

        fnac = parse_fecha(t)
        edad = edad_from_fecha_nacimiento(fnac) if fnac else None

        something = False
        if nombre:
            _set(patch, "ficha.datos.nombre_completo", nombre)
            something = True
        if fnac:
            _set(patch, "ficha.datos.fecha_nacimiento", fnac.isoformat())
            something = True
        if edad is not None:
            _set(patch, "ficha.datos.edad", edad)
            something = True

        # sólo si extrajimos algo del bloque DATOS, seteamos fecha_evaluacion
        if something:
            _set(patch, "ficha.datos.fecha_evaluacion", _now_date().isoformat())

    elif name == "ANTROPOMETRIA":
        peso = parse_peso_kg(text)
        talla = parse_talla_cm(text)
        if peso is not None:
            _set(patch, "ficha.antropometria.peso_kg", peso)
        if talla is not None:
            _set(patch, "ficha.antropometria.talla_cm", talla)
        imc = calc_imc(
            peso if peso is not None else state.ficha.antropometria.peso_kg,
            talla if talla is not None else state.ficha.antropometria.talla_cm
        )
        if imc is not None:
            _set(patch, "ficha.antropometria.imc", imc)

    elif name == "COBERTURA":
        afiliado = parse_afiliado(text)
        if afiliado:
            _set(patch, "ficha.cobertura.afiliado", afiliado)
        t = (text or "").strip()
        if t and len(t) >= 3:
            if not state.ficha.cobertura.obra_social:
                _set(patch, "ficha.cobertura.obra_social", t[:80])
            if not state.ficha.cobertura.motivo_cirugia:
                _set(patch, "ficha.cobertura.motivo_cirugia", t[:160])

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

    # —— antibucle: resetear sólo si llenamos algún requerido que faltaba
    if patch:
        filled_required = any(_get(patch, path) not in (None, "", [], {}) for path in missing_before)
        if filled_required:
            _reset_retry(state, module_idx)
        else:
            _inc_retry(state, module_idx)
    else:
        _inc_retry(state, module_idx)

    return patch  # <- OJO: sin envolver en {"ficha": ...}

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

    # —— antibucle para módulos con LLM también:
    if patch:
        _reset_retry(state, module_idx)
    else:
        _inc_retry(state, module_idx)

    return patch

# ===== Avance y mensajes =====

def advance_module(state: ConversationState) -> Tuple[Optional[int], Optional[str]]:
    """Devuelve (next_idx, next_prompt) o (None, None) si terminó.
       Antibucle: si supera MAX_RETRIES en un módulo obligatorio, AVANZA y pide el prompt del siguiente."""
    for i in range(state.module_idx, len(MODULES)):
        missing = _missing_required(state, i)
        if missing:
            retries = _retries(state, i)
            if retries >= MAX_RETRIES:
                # avanzar al próximo módulo para cortar cualquier loop
                next_idx = min(i + 1, len(MODULES) - 1)
                _reset_retry(state, i)
                # Pedimos directamente el prompt del siguiente módulo
                return next_idx, prompt_for_module(next_idx)
            # caso normal: pedir input del módulo actual
            return i, prompt_for_module(i)
        # si el módulo actual no tiene faltantes, seguimos al próximo
        continue
    # si no quedan módulos con faltantes, terminamos
    return None, None

def prompt_for_module(module_idx: int) -> str:
    name = MODULES[module_idx]["name"]
    prompts = {
        "DNI": "Decime tu DNI (solo números, sin puntos ni espacios). Ej: 12345678",
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
    def val(x, placeholder="—"):
        return placeholder if x in (None, "", [], {}) else x

    name = MODULES[module_idx]["name"]
    try:
        if name == "DNI":
            d = patch.get("ficha", {}).get("dni")
            if not d:
                return "No pude extraer un DNI. Escribilo SOLO con números, sin puntos ni espacios. Ej: 12345678"
            return f"Anoté DNI: {val(d)}"
        if name == "DATOS":
            d = patch.get("ficha", {}).get("datos", {})
            return (
                f"Anoté: {val(d.get('nombre_completo'))}, "
                f"nac. {val(d.get('fecha_nacimiento'))}, "
                f"edad {val(d.get('edad'))}"
            )
        if name == "ANTROPOMETRIA":
            a = patch.get("ficha", {}).get("antropometria", {})
            return (
                f"Anoté: peso {val(a.get('peso_kg'))} kg, "
                f"talla {val(a.get('talla_cm'))} cm, "
                f"IMC {val(a.get('imc'))}"
            )
        if name == "COBERTURA":
            c = patch.get("ficha", {}).get("cobertura", {})
            return (
                f"Anoté: OS {val(c.get('obra_social'))}, "
                f"afiliado {val(c.get('afiliado'))}, "
                f"motivo {val(c.get('motivo_cirugia'))}"
            )
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
    base = json.loads(state.ficha.model_dump_json())

    def rec_merge(dst, src):
        for k, v in src.items():
            if isinstance(v, dict) and isinstance(dst.get(k), dict):
                rec_merge(dst[k], v)
            else:
                dst[k] = v

    rec_merge(base, patch.get("ficha", {}) if "ficha" in patch else patch)
    state.ficha = FichaPreanestesia(**base)
    return state
