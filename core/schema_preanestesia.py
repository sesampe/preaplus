# core/schema_preanestesia.py
## ESTO LO QUE HACE ES QUE LOS DATOS TENGAN UN BUEN FORMATO = PYDANTIC

from typing import Optional, List
from pydantic import BaseModel, Field

# --- Bloques base (lo que ya tenías) ---
class Paciente(BaseModel):
    nombre_completo: str = ""
    dni: str = ""
    fecha_nacimiento: str = "DD/MM/AAAA"
    telefono: str = ""
    email: str = ""
    direccion: str = ""

class Antropometria(BaseModel):
    peso_kg: Optional[float] = None
    talla_cm: Optional[float] = None
    imc: Optional[float] = None

class Procedimiento(BaseModel):
    descripcion: str = ""
    fecha_prevista: str = "DD/MM/AAAA"
    institucion: str = ""

class Tabaquismo(BaseModel):
    tabaquista: bool = False
    paquetes_anio: Optional[float] = None

class Alcohol(BaseModel):
    consumo: bool = False
    frecuencia: str = ""

class AntecedentesMedicos(BaseModel):
    hta: bool = False
    diabetes: bool = False
    asma_epoc: bool = False
    cardiopatia: bool = False
    apnea_sueno: bool = False
    tabaquismo: Tabaquismo = Tabaquismo()
    alcohol: Alcohol = Alcohol()
    otros: str = ""

class AlergiaDetalle(BaseModel):
    sustancia: str = ""
    reaccion: str = ""

class Alergias(BaseModel):
    tiene_alergias: bool = False
    detalles: List[AlergiaDetalle] = Field(default_factory=list)

class MedicacionItem(BaseModel):
    nombre: str = ""
    dosis: str = ""
    horario: str = ""

class AntecedentesAnestesicos(BaseModel):
    complicaciones_previas: bool = False
    detalle: str = ""
    nvpo_previo: bool = False
    intubacion_dificil_previa: bool = False

class Ayuno(BaseModel):
    ultimos_solidos: str = "DD/MM/AAAA HH:MM"
    ultimos_liquidos_claros: str = "DD/MM/AAAA HH:MM"

class EstudioSimple(BaseModel):
    fecha: str = "DD/MM/AAAA"
    resultado: str = ""

class Estudios(BaseModel):
    laboratorio: EstudioSimple = EstudioSimple()
    ecg: EstudioSimple = EstudioSimple()
    rx_torax: EstudioSimple = EstudioSimple()

class ViaAerea(BaseModel):
    mallampati: str = ""                       # I–IV (texto libre permitido)
    apertura_bucal_cm: Optional[float] = None  # “APERTURA ORAL” :contentReference[oaicite:4]{index=4}
    movilidad_cervical: str = ""               # >35° / <35° :contentReference[oaicite:5]{index=5}
    protesis_dentales: bool = False

# --- Extensiones del PDF ---
class ViaAereaExtendida(ViaAerea):
    antecedente_intubacion_dificultosa: Optional[bool] = None   # :contentReference[oaicite:6]{index=6}
    dientes_flojos: Optional[bool] = None                       # :contentReference[oaicite:7]{index=7}
    protesis_dental: Optional[bool] = None                      # PDF usa “prótesis dental” SI/NO :contentReference[oaicite:8]{index=8}
    distancia_tiromentoniana_cm: Optional[float] = None         # >6,5 / <6,5 :contentReference[oaicite:9]{index=9}
    test_mordida: str = ""                                      # >0, =0, <0 :contentReference[oaicite:10]{index=10}
    # Factores de ventilación dificultosa:
    obesidad_imc_mayor_26: bool = False
    barba: bool = False
    edad_mayor_55: bool = False
    saos_roncador: bool = False
    edentado: bool = False

class ExamenesComplementariosValores(BaseModel):
    hb: Optional[float] = None
    hto: Optional[float] = None
    plt: Optional[float] = None
    gb: Optional[float] = None
    tp: Optional[float] = None
    ttpK: Optional[float] = None
    fibrinogeno: Optional[float] = None
    uremia: Optional[float] = None
    creatininemia: Optional[float] = None
    glucemia: Optional[float] = None

class ExamenesComplementarios(BaseModel):
    hemograma: str = ""
    coagulograma: str = ""
    urograma: str = ""
    ecg: str = ""
    otros: str = ""
    valores: ExamenesComplementariosValores = ExamenesComplementariosValores()

class EvaluacionPreoperatoria(BaseModel):
    asa: str = "I"                                # 1–6 / U en PDF :contentReference[oaicite:11]{index=11}
    requiere_cama_uti: Optional[bool] = None      # :contentReference[oaicite:12]{index=12}
    disponibilidad_hemoderivados: Optional[bool] = None

class ConsumoSustanciasIlicitas(BaseModel):
    si: bool = False
    detalle: str = ""

class Embarazo(BaseModel):
    aplica: bool = False
    semanas: Optional[int] = None

class FichaPreanestesia(BaseModel):
    paciente: Paciente = Paciente()
    antropometria: Antropometria = Antropometria()
    procedimiento: Procedimiento = Procedimiento()
    antecedentes_medicos: AntecedentesMedicos = AntecedentesMedicos()
    alergias: Alergias = Alergias()
    medicacion_actual: List[MedicacionItem] = Field(default_factory=list)
    antecedentes_anestesicos: AntecedentesAnestesicos = AntecedentesAnestesicos()
    ayuno: Ayuno = Ayuno()
    estudios: Estudios = Estudios()
    via_aerea: ViaAereaExtendida = ViaAereaExtendida()
    # Extensiones del PDF:
    examenes_complementarios: ExamenesComplementarios = ExamenesComplementarios()
    evaluacion_preoperatoria: EvaluacionPreoperatoria = EvaluacionPreoperatoria()
    consumo_sustancias_ilicitas: ConsumoSustanciasIlicitas = ConsumoSustanciasIlicitas()
    embarazo: Embarazo = Embarazo()
    observaciones: str = ""
