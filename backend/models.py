"""
NeoAccess - Modelos de Pydantic para Validación de Datos
Ubicación: C:\\Users\\gr321\\Desktop\\NeoAccess\\backend\\models.py
"""

from pydantic import BaseModel, Field
from typing import Optional, List, Literal

class LoginRequest(BaseModel):
    username: str
    password: str

class LabCreate(BaseModel):
    id: str
    nombre: str
    edificio: str
    carrera: str
    capacidad: Optional[int] = 30
    descripcion: Optional[str] = None

class LabUpdate(BaseModel):
    nombre: str
    edificio: str
    carrera: str
    capacidad: Optional[int] = 30
    descripcion: Optional[str] = None
    activo: Optional[int] = 1

class DeviceCreate(BaseModel):
    id: str
    laboratorio_id: str
    nombre: str
    ip_address: Optional[str] = "192.168.1.100"
    mac_address: Optional[str] = "B8:27:EB:00:00:00"
    intervalo_latido_seg: Optional[int] = 300

class GroupCreate(BaseModel):
    id: str
    nombre: str
    carrera: str
    semestre: int

class UserCreate(BaseModel):
    id: str
    nombre_completo: str
    tipo: str # 'alumno', 'docente', 'personal_limpieza', 'administrador'
    matricula_clave: str
    carrera: Optional[str] = None
    grupo_id: Optional[str] = None
    estado: Optional[str] = "activo"

class FacialMetadataCreate(BaseModel):
    usuario_id: str
    vector_encoding: List[float] # Vector 128-d (sin imágenes)
    calidad_muestra: Optional[float] = 1.0

class FacialCapturePayload(BaseModel):
    imagenes: List[str]  # Fotogramas JPEG en base64 (se procesan en RAM y se descartan)

class ScheduleCreate(BaseModel):
    grupo_id: Optional[str] = None
    laboratorio_id: str
    docente_id: str
    materia: str
    dia_semana: str # Lunes, Martes, Miércoles, Jueves, Viernes, Sábado
    hora_inicio: str # '08:00'
    hora_fin: str # '10:00'

class HeartbeatPayload(BaseModel):
    dispositivo_id: str
    token_api: str
    ip_address: Optional[str] = None
    cpu_temp: Optional[float] = None
    mem_usage: Optional[float] = None
    timestamp: Optional[str] = None

class AccessAttemptPayload(BaseModel):
    dispositivo_id: str
    token_api: str
    usuario_id: Optional[str] = None
    resultado: Literal["permitido", "denegado"]
    motivo: str
    fecha_hora: Optional[str] = None
    sincronizado_offline: Optional[bool] = False

class CleaningPayload(BaseModel):
    dispositivo_id: str
    token_api: str
    personal_id: str
    accion: Literal["entrada", "salida"]
    fecha_hora: Optional[str] = None

class CommandAckPayload(BaseModel):
    dispositivo_id: str
    exito: bool = True
    detalle: Optional[str] = None
