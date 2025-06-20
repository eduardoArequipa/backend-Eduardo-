# backEnd/app/schemas/persona.py
from pydantic import BaseModel, Field, EmailStr, ConfigDict
from typing import Optional
from datetime import datetime
from ..models.enums import EstadoEnum, GeneroEnum 

from typing import Optional, List 
from app.models.enums import EstadoEnum, GeneroEnum
from app.models.usuario import EstadoEnum as UsuarioEstadoEnum

class UsuarioCreateOptional(BaseModel):
    nombre_usuario: str = Field(..., min_length=1, max_length=50, description="Nombre de usuario para el nuevo Usuario")
    contraseña: str = Field(..., min_length=6, description="Contraseña para el nuevo Usuario")
    estado: Optional[EstadoEnum] = Field(EstadoEnum.activo, description="Estado inicial del Usuario (activo, inactivo, bloqueado)") # Usamos el Enum global EstadoEnum
    foto_ruta: Optional[str] = Field(None, description="Ruta a la foto de perfil del Usuario")
    rol_ids: List[int] = Field(default_factory=list, description="Lista de IDs de Roles a asignar al Usuario inmediatamente")


class PersonaBase(BaseModel):
    nombre: str = Field(..., min_length=1, max_length=100)
    apellido_paterno: Optional[str] = Field(None, max_length=100)
    apellido_materno: Optional[str] = Field(None, max_length=100)
    ci: Optional[str] = Field(None, max_length=20)
    genero: Optional[GeneroEnum] = None
    telefono: Optional[str] = Field(None, max_length=20)
    email: Optional[EmailStr] = Field(None, max_length=100)
    direccion: Optional[str] = None
    estado: Optional[EstadoEnum] = EstadoEnum.activo 

class PersonaCreate(PersonaBase):
    nombre: str = Field(..., min_length=1, max_length=100) 

    usuario_data: Optional[UsuarioCreateOptional] = Field(None, description="Datos opcionales para crear un Usuario asociado y roles")


class Persona(PersonaBase):
    persona_id: int
    model_config = ConfigDict(from_attributes=True)

# Esquema para incluir Persona anidada (usado en schemas/usuario.py)
class PersonaNested(PersonaBase):
     persona_id: int
     model_config = ConfigDict(from_attributes=True)


class PersonaUpdate(PersonaBase):
     # Hereda 
     pass