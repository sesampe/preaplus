import os
from pathlib import Path
from dotenv import load_dotenv

# 1) Cargar .env ANTES de leer variables
load_dotenv()

# === Constantes de proveedor/modelos ===
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "openai")

CLAUDE_API_KEY = os.getenv("CLAUDE_API_KEY", "")
CLAUDE_MODEL = os.getenv("CLAUDE_MODEL", "claude-3-7-sonnet-20250219")

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")

# === System Prompt ===
SYSTEM_PROMPT_FILE = os.getenv("SYSTEM_PROMPT_FILE", "").strip() or None
SYSTEM_PROMPT_ENV = os.getenv("SYSTEM_PROMPT", "")

def _load_system_prompt():
    """
    Prioridad:
    1) Archivo especificado por SYSTEM_PROMPT_FILE
    2) Variable de entorno SYSTEM_PROMPT
    Retorna string (sin BOM/espacios) o "" si no hay nada.
    """
    # A) desde archivo si existe
    if SYSTEM_PROMPT_FILE:
        p = Path(SYSTEM_PROMPT_FILE)
        if p.is_file():
            try:
                return p.read_text(encoding="utf-8").strip()
            except Exception:
                # fallback al env si falla la lectura
                pass

    # B) desde env como fallback
    return (SYSTEM_PROMPT_ENV or "").strip()

SYSTEM_PROMPT = _load_system_prompt()

# === Resto de configuración de tu app ===
PRODUCT_LIST_FILE_ID = os.getenv("PRODUCT_LIST_FILE_ID")
CATALOG_PDF_FILE_ID = os.getenv("CATALOG_PDF_FILE_ID")
CATALOG_PDF_LINK = f"https://drive.google.com/file/d/{CATALOG_PDF_FILE_ID}/view?usp=sharing"
SERVICE_ACCOUNT_FILE = "service-account-key.json"
PRODUCTS_CACHE_FILE = "data/products_cache.json"

HEYOO_TOKEN = os.getenv("HEYOO_TOKEN")
HEYOO_PHONE_ID = os.getenv("HEYOO_PHONE_ID")
OWNER_PHONE_NUMBER = os.getenv("OWNER_PHONE_NUMBER")

CONVERSATION_HISTORY_DIR = "data/conversation_histories"
TAKEOVER_FILE = "data/takeover_status.json"

APP_SECRET = os.getenv("APP_SECRET")


# === Molde de salida para evaluación preanestésica (JSON) ===
PREANESTHESIA_SCHEMA = r'''
{
  "datos": {
    "fecha_evaluacion": "DD/MM/AAAA",
    "nombre_apellido": "",
    "fecha_nacimiento": "DD/MM/AAAA",
    "edad_anios": null,
    "peso_kg": null,
    "talla_cm": null,
    "imc": null,
    "dni": "",
    "obra_social": "",
    "numero_afiliado": ""
  },
  "motivo_consulta_intervencion": "",
  "antecedentes_patologicos": {
    "alergicos": "",
    "cardiovasculares": "",
    "respiratorio": "",
    "urologicos": "",
    "hematologicos": "",
    "endocrino_metabolico": "",
    "neurologicos": "",
    "quirurgicos": "",
    "psiquiatricos": "",
    "infecciosos": "",
    "perinatales": "",
    "gastrointestinales": "",
    "posibilidad_embarazo": { "aplica": false, "fecha_ultima_menstruacion": "DD/MM/AAAA" },
    "otros": ""
  },
  "medicacion_habitual": "",
  "consumo_sustancias_ilicitas": { "si": false, "detalle": "" },
  "via_aerea": {
    "antecedente_intubacion_dificultosa": null,
    "dientes_flojos": null,
    "protesis_dental": null,
    "mallampati": "",
    "test_mordida": { "mayor_0": null, "igual_0": null, "menor_0": null },
    "apertura_oral_cm": null,
    "distancia_tiromentoniana_cm": null,
    "movilidad_cervical": { "mayor_35": null, "menor_35": null },
    "factores_ventilacion_dificultosa": {
      "obesidad_imc_mayor_26": false,
      "barba": false,
      "edad_mayor_55": false,
      "saos_roncador": false,
      "edentado": false
    }
  },
  "examenes_complementarios": {
    "hemograma": "",
    "coagulograma": "",
    "urograma": "",
    "ecg": "",
    "otros": "",
    "valores": {
      "hb": null, "hto": null, "plt": null, "gb": null,
      "tp": null, "ttkp": null, "fibrinogeno": null,
      "uremia": null, "creatininemia": null, "glucemia": null
    }
  },
  "evaluacion_preoperatoria": {
    "asa": "",
    "requiere_cama_uti": null,
    "disponibilidad_hemoderivados": null
  },
  "observaciones": ""
}
'''

# Dónde guardamos temporales de PDF (local)
PDF_TMP_DIR = "tmp_pdfs"

# (Opcional) Si ya tenés una plantilla PDF para llenar:
PDF_TEMPLATE_PATH = os.getenv("PDF_TEMPLATE_PATH", "")  # ruta a tu PDF con campos (si no, queda "")
