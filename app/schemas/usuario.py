# backEnd/app/schemas/usuario.py
from pydantic import BaseModel, Field, ConfigDict
from typing import Optional, List
from datetime import datetime
from ..models.enums import EstadoEnum
from .persona import PersonaNested
from .rol import RolNested

class UsuarioBase(BaseModel):
    nombre_usuario: str = Field(..., min_length=1, max_length=50)
    estado: Optional[EstadoEnum] = EstadoEnum.activo
    foto_ruta: Optional[str] = None

class UsuarioCreate(UsuarioBase):
    persona_id: int = Field(..., description="ID de la Persona asociada a este Usuario")
    nombre_usuario: str = Field(..., min_length=1, max_length=50)
    contraseña: str = Field(..., min_length=6)

class UsuarioUpdate(UsuarioBase):
    contraseña: Optional[str] = Field(None, min_length=6)


class UsuarioAudit(BaseModel):
     usuario_id: int
     nombre_usuario: str
     model_config = ConfigDict(from_attributes=True)

class Usuario(UsuarioBase):
    usuario_id: int
    persona_id: int
    intentos_fallidos: int
    bloqueado_hasta: Optional[datetime]
    creado_por: Optional[int]

    codigo_recuperacion: Optional[str] = None
    expiracion_codigo_recuperacion: Optional[datetime] = None

    persona: Optional[PersonaNested] = None
    roles: List[RolNested] = []

    model_config = ConfigDict(from_attributes=True)

class UsuarioReadAudit(Usuario): 
    creador: Optional[UsuarioAudit] = None

    model_config = ConfigDict(from_attributes=True)