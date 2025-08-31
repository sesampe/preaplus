import os
from dotenv import load_dotenv
from pathlib import Path

SYSTEM_PROMPT = os.getenv("SYSTEM_PROMPT", "")
SYSTEM_PROMPT_FILE = os.getenv("SYSTEM_PROMPT_FILE")

# Carga las variables desde el archivo .env
load_dotenv()

# Configuración del proveedor de IA
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "openai")

# Configuración LLM
CLAUDE_API_KEY = os.getenv("CLAUDE_API_KEY","")
CLAUDE_MODEL = os.getenv("CLAUDE_MODEL", "claude-3-7-sonnet-20250219")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY","")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")
SYSTEM_PROMPT = os.getenv("SYSTEM_PROMPT", "")

# Google Drive
PRODUCT_LIST_FILE_ID = os.getenv("PRODUCT_LIST_FILE_ID")
CATALOG_PDF_FILE_ID = os.getenv("CATALOG_PDF_FILE_ID")
CATALOG_PDF_LINK = f"https://drive.google.com/file/d/{CATALOG_PDF_FILE_ID}/view?usp=sharing"
SERVICE_ACCOUNT_FILE = "service-account-key.json"
PRODUCTS_CACHE_FILE = "data/products_cache.json"

# WhatsApp via Heyoo
HEYOO_TOKEN = os.getenv("HEYOO_TOKEN")
HEYOO_PHONE_ID = os.getenv("HEYOO_PHONE_ID")
OWNER_PHONE_NUMBER = os.getenv("OWNER_PHONE_NUMBER")

# Conversaciones
CONVERSATION_HISTORY_DIR = "data/conversation_histories"
TAKEOVER_FILE = "data/takeover_status.json"

APP_SECRET = os.getenv("APP_SECRET")  # Cambia esto por tu secreto real


# === Molde de salida para evaluación preanestésica (JSON) ===
PREANESTHESIA_SCHEMA = r'''
{
  "paciente": {
    "nombre_completo": "",
    "dni": "",
    "fecha_nacimiento": "DD/MM/AAAA",
    "telefono": "",
    "email": "",
    "direccion": ""
  },
  "antropometria": { "peso_kg": null, "talla_cm": null, "imc": null },
  "procedimiento": { "descripcion": "", "fecha_prevista": "DD/MM/AAAA", "institucion": "" },
  "antecedentes_medicos": {
    "hta": false, "diabetes": false, "asma_epoc": false, "cardiopatia": false,
    "apnea_sueno": false,
    "tabaquismo": { "tabaquista": false, "paquetes_anio": null },
    "alcohol": { "consumo": false, "frecuencia": "" },
    "otros": ""
  },
  "alergias": {
    "tiene_alergias": false,
    "detalles": [ { "sustancia": "", "reaccion": "" } ]
  },
  "medicacion_actual": [ { "nombre": "", "dosis": "", "horario": "" } ],
  "antecedentes_anestesicos": {
    "complicaciones_previas": false, "detalle": "",
    "nvpo_previo": false, "intubacion_dificil_previa": false
  },
  "ayuno": { "ultimos_solidos": "DD/MM/AAAA HH:MM", "ultimos_liquidos_claros": "DD/MM/AAAA HH:MM" },
  "estudios": {
    "laboratorio": { "fecha": "DD/MM/AAAA", "resumen": "" },
    "ecg": { "fecha": "DD/MM/AAAA", "resultado": "" },
    "rx_torax": { "fecha": "DD/MM/AAAA", "resultado": "" }
  },
  "via_aerea": { "mallampati": "", "apertura_bucal_cm": null, "movilidad_cervical": "", "protesis_dentales": false },
  "asa": "I",
  "embarazo": { "aplica": false, "semanas": null },
  "observaciones": ""
}
'''

# Dónde guardamos temporales de PDF (local)
PDF_TMP_DIR = "tmp_pdfs"

# (Opcional) Si ya tenés una plantilla PDF para llenar:
PDF_TEMPLATE_PATH = os.getenv("PDF_TEMPLATE_PATH", "")  # ruta a tu PDF con campos (si no, queda "")
