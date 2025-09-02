# schemas.py
from typing import List, Optional, Dict
from pydantic import BaseModel, Field
from datetime import date, datetime

# ===== Bloques =====

class Datos(BaseModel):
    nombre_completo: Optional[str] = None
    fecha_nacimiento: Optional[date] = None
    edad: Optional[int] = None
    fecha_evaluacion: Optional[date] = None

class Antropometria(BaseModel):
    peso_kg: Optional[float] = None
    talla_cm: Optional[float] = None
    imc: Optional[float] = None
    asa: Optional[str] = None  # se deja manual

class Cobertura(BaseModel):
    obra_social: Optional[str] = None
    afiliado: Optional[str] = None
    motivo_cirugia: Optional[str] = None

class AlergiaItem(BaseModel):
    sustancia: str
    reaccion: Optional[str] = None

class Alergias(BaseModel):
    tiene_alergias: bool
    detalle: List[AlergiaItem] = Field(default_factory=list)

class MedicacionItem(BaseModel):
    droga: str
    dosis: Optional[str] = None
    frecuencia: Optional[str] = None

class AlergiaMedicacion(BaseModel):
    alergias: Alergias
    medicacion_habitual: List[MedicacionItem] = Field(default_factory=list)

class Cardio(BaseModel):
    hta: Optional[bool] = None
    iam: Optional[bool] = None
    falla_card: Optional[bool] = None
    otros: List[str] = Field(default_factory=list)

class Respiratorio(BaseModel):
    epoc: Optional[bool] = None
    asma: Optional[bool] = None
    apnea_sueño: Optional[bool] = None
    otros: List[str] = Field(default_factory=list)

class Endocrino(BaseModel):
    dm: Optional[bool] = None
    hipotiroidismo: Optional[bool] = None
    hipertiroidismo: Optional[bool] = None
    otros: List[str] = Field(default_factory=list)

class Renal(BaseModel):
    irc: Optional[bool] = None
    dialisis: Optional[bool] = None
    otros: List[str] = Field(default_factory=list)

class Neuro(BaseModel):
    acv: Optional[bool] = None
    convulsiones: Optional[bool] = None
    otros: List[str] = Field(default_factory=list)

class Antecedentes(BaseModel):
    cardio: Optional[Cardio] = None
    respiratorio: Optional[Respiratorio] = None
    endocrino: Optional[Endocrino] = None
    renal: Optional[Renal] = None
    neuro: Optional[Neuro] = None
    otros: List[str] = Field(default_factory=list)

class LabOtro(BaseModel):
    nombre: str
    valor: str

class ImagenItem(BaseModel):
    estudio: str
    hallazgo: Optional[str] = None

class Labs(BaseModel):
    hb: Optional[float] = None
    plaquetas: Optional[int] = None
    creatinina: Optional[float] = None
    inr: Optional[float] = None
    otros: List[LabOtro] = Field(default_factory=list)

class Complementarios(BaseModel):
    labs: Labs = Field(default_factory=Labs)
    imagenes: List[ImagenItem] = Field(default_factory=list)

class Tabaquismo(BaseModel):
    consume: Optional[bool] = None
    paquetes_dia: Optional[float] = None
    anos_paquete: Optional[float] = None
    ultimo_consumo: Optional[str] = None

class Alcohol(BaseModel):
    consume: Optional[bool] = None
    tragos_semana: Optional[float] = None

class OtrasSustancias(BaseModel):
    consume: Optional[bool] = None
    detalle: List[str] = Field(default_factory=list)

class Sustancias(BaseModel):
    tabaco: Tabaquismo = Field(default_factory=Tabaquismo)
    alcohol: Alcohol = Field(default_factory=Alcohol)
    otras: OtrasSustancias = Field(default_factory=OtrasSustancias)

class ViaAerea(BaseModel):
    intubacion_dificil: Optional[bool] = None
    piezas_flojas: Optional[bool] = None
    protesis: Optional[bool] = None
    otros: List[str] = Field(default_factory=list)

# ===== Ficha completa =====

class FichaPreanestesia(BaseModel):
    dni: Optional[str] = None
    datos: Datos = Field(default_factory=Datos)
    antropometria: Antropometria = Field(default_factory=Antropometria)
    cobertura: Cobertura = Field(default_factory=Cobertura)
    alergia_medicacion: Optional[AlergiaMedicacion] = None
    antecedentes: Optional[Antecedentes] = None
    complementarios: Complementarios = Field(default_factory=Complementarios)
    sustancias: Sustancias = Field(default_factory=Sustancias)
    via_aerea: ViaAerea = Field(default_factory=ViaAerea)

# ===== Estado de conversación (workflow modular) =====

class ConversationState(BaseModel):
    user_id: str
    module_idx: int = 0
    ficha: FichaPreanestesia = Field(default_factory=FichaPreanestesia)
    trace: Dict[str, Dict[str, str]] = Field(default_factory=dict)  # module.field -> raw text
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

# ===== Contexto de conversación (servicio de chat) =====

class ConversationContext(BaseModel):
    customer_phone: str
    last_message_timestamp: datetime
    last_intent: Optional[str] = None
    current_order_id: Optional[str] = None
    human_takeover: bool = False
