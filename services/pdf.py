import os
from datetime import datetime
from typing import Dict, Any

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

from core.settings import PDF_TMP_DIR, PDF_TEMPLATE_PATH

# Explicación: este generador hace un PDF simple “bonito” con los datos.
# Luego, cuando tengas el PDF plantilla (con campos), cambiamos esta función
# por una que “rellene campos” en lugar de dibujar texto.

def ensure_tmp_dir():
    os.makedirs(PDF_TMP_DIR, exist_ok=True)

def _draw_kv(c: canvas.Canvas, x: int, y: int, key: str, value: str):
    c.setFont("Helvetica-Bold", 10)
    c.drawString(x, y, f"{key}:")
    c.setFont("Helvetica", 10)
    c.drawString(x + 140, y, value if value is not None else "")

def build_preanesthesia_pdf(data: Dict[str, Any]) -> str:
    """
    Genera un PDF simple con los datos. Devuelve la ruta del archivo PDF.
    data: diccionario con las claves del schema (paciente, antropometria, etc.)
    """
    ensure_tmp_dir()
    paciente = data.get("paciente", {})
    phone = paciente.get("telefono", "") or data.get("telefono", "")
    nombre = paciente.get("nombre_completo", "Paciente")

    ts = datetime.now().strftime("%Y%m%d-%H%M")
    filename = f"Preanestesia_{nombre.replace(' ', '_')}_{ts}.pdf"
    filepath = os.path.join(PDF_TMP_DIR, filename)

    c = canvas.Canvas(filepath, pagesize=A4)
    width, height = A4

    # Título
    c.setFont("Helvetica-Bold", 16)
    c.drawString(40, height - 60, "Evaluación Preanestésica")

    c.setFont("Helvetica", 9)
    c.drawString(40, height - 75, f"Generado: {datetime.now().strftime('%d/%m/%Y %H:%M')}")

    y = height - 110

    # Secciones básicas (podés ajustar orden/rótulos)
    sections = [
        ("Datos del paciente", data.get("paciente", {})),
        ("Antropometría", data.get("antropometria", {})),
        ("Procedimiento", data.get("procedimiento", {})),
        ("Antecedentes médicos", data.get("antecedentes_medicos", {})),
        ("Alergias", data.get("alergias", {})),
        ("Medicación actual", {"items": data.get("medicacion_actual", [])}),
        ("Antecedentes anestésicos", data.get("antecedentes_anestesicos", {})),
        ("Ayuno", data.get("ayuno", {})),
        ("Estudios", data.get("estudios", {})),
        ("Vía aérea", data.get("via_aerea", {})),
        ("ASA", {"asa": data.get("asa", "")}),
        ("Embarazo", data.get("embarazo", {})),
        ("Observaciones", {"texto": data.get("observaciones", "")}),
    ]

    for title, content in sections:
        c.setFont("Helvetica-Bold", 12)
        c.drawString(40, y, title)
        y -= 16
        c.setFont("Helvetica", 10)

        # Render plano/recursivo básico
        if isinstance(content, dict):
            for k, v in content.items():
                # listas (ej. medicación)
                if isinstance(v, list):
                    _draw_kv(c, 40, y, k, "")
                    y -= 14
                    for item in v:
                        c.drawString(60, y, f"- {item}")
                        y -= 12
                else:
                    _draw_kv(c, 40, y, k, str(v) if v is not None else "")
                    y -= 14
        else:
            c.drawString(40, y, str(content))
            y -= 14

        y -= 6
        if y < 120:  # salto de página si falta espacio
            c.showPage()
            y = height - 60

    c.showPage()
    c.save()
    return filepath
