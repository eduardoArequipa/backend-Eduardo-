# backEnd/app/schemas/usuario.py

from pydantic import BaseModel, Field, ConfigDict
from typing import Optional, List
from datetime import datetime
from ..models.enums import EstadoEnum
from .pagination import Pagination # Importar la clase Pagination

# Importamos esquemas de otros módulos. Usamos RolInDB para ser explícitos.
from .persona import PersonaBase, PersonaWithRoles # Para anidar la información de la Persona
from .rol import RolInDB # <-- ¡CAMBIO AQUÍ! (Usamos RolInDB para los roles del usuario)

# --- Esquema base para Usuario ---
class UsuarioBase(BaseModel):
    nombre_usuario: str = Field(..., min_length=1, max_length=50, description="Nombre de usuario, debe ser único")
    estado: Optional[EstadoEnum] = EstadoEnum.activo # Estado del usuario (activo, inactivo, bloqueado)
    foto_ruta: Optional[str] = None # Ruta opcional a la foto de perfil

# --- Esquema para crear un Usuario ---
class UsuarioCreate(UsuarioBase):
    """
    Esquema para crear un nuevo Usuario.
    Requiere una persona_id existente a la cual se vinculará este usuario.
    """
    persona_id: int = Field(..., description="ID de la Persona asociada a este Usuario")
    contraseña: str = Field(..., min_length=6, description="Contraseña para el usuario")


# --- Esquema para actualizar un Usuario ---
class UsuarioUpdate(UsuarioBase):
    """
    Esquema para actualizar los datos de un Usuario.
    Todos los campos son opcionales para permitir actualizaciones parciales.
    """
    nombre_usuario: Optional[str] = Field(None, min_length=1, max_length=50) # Hacemos opcional para PATCH
    contraseña: Optional[str] = Field(None, min_length=6, description="Nueva contraseña para el usuario")
    estado: Optional[EstadoEnum] = None # Permitir cambiar el estado del usuario
    foto_ruta: Optional[str] = None

# --- Esquema para auditoría de Usuario (versión anidada) ---
class UsuarioAudit(BaseModel):
     usuario_id: int
     nombre_usuario: str
     model_config = ConfigDict(from_attributes=True)

# --- Esquema principal para Usuario (respuesta de lectura) ---
class Usuario(UsuarioBase):
    """
    Esquema para representar un Usuario tal como se lee de la base de datos,
    incluyendo su ID y las relaciones clave.
    """
    usuario_id: int
    persona_id: int
    intentos_fallidos: int
    bloqueado_hasta: Optional[datetime]
    creado_por: Optional[int] # ID del usuario que creó este usuario

    codigo_recuperacion: Optional[str] = None
    expiracion_codigo_recuperacion: Optional[datetime] = None

    # Relación a la Persona asociada (anidada)
    persona: Optional[PersonaWithRoles] = None # <-- ¡CLARIFICADO!


    model_config = ConfigDict(from_attributes=True)

# --- Esquema para Usuario con detalles de auditoría del creador ---
class UsuarioReadAudit(BaseModel):
    usuario_id: int
    nombre_usuario: str
    estado: str # O EstadoEnum
    foto_ruta: Optional[str] = None
    persona_id: int
    intentos_fallidos: int
    bloqueado_hasta: Optional[datetime] = None
    creado_por: Optional[int] = None
    codigo_recuperacion: Optional[str] = None
    expiracion_codigo_recuperacion: Optional[datetime] = None

    persona: Optional[PersonaBase] = None # Esto es crucial


    creador: Optional["UsuarioBase"] = None 


    class Config:
        from_attributes = True

class UsuarioPagination(Pagination[Usuario]):
    """Esquema para la respuesta paginada de usuarios."""
    pass
