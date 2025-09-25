# backEnd/app/schemas/rol.py

from pydantic import BaseModel, Field, ConfigDict
from typing import Optional, List
from ..models.enums import EstadoEnum
from .menu import MenuInDB

# --- Esquema base para Rol ---
class RolBase(BaseModel):
    rol_id: int
    nombre_rol: str = Field(..., min_length=3, max_length=50, description="Nombre único del rol")
    descripcion: Optional[str] = Field(None, description="Descripción detallada del rol")
    estado: Optional[EstadoEnum] = EstadoEnum.activo

# --- Esquema para crear un Rol ---
class RolCreate(RolBase):
    """Esquema para crear un nuevo Rol."""
    pass

# --- Esquema para actualizar un Rol ---
class RolUpdate(BaseModel):
    """
    Esquema para actualizar los datos de un Rol.
    Todos los campos son opcionales para permitir actualizaciones parciales.
    """
    nombre_rol: Optional[str] = Field(None, min_length=3, max_length=50)
    descripcion: Optional[str] = None
    estado: Optional[EstadoEnum] = None

# --- Esquema para representar un Rol leído de la base de datos ---
class RolInDB(RolBase):
    rol_id: int
    menus: List[MenuInDB] = []  # Lista de menús asignados al rol

    model_config = ConfigDict(from_attributes=True)

# --- Esquema simplificado para Rol (anidado) ---
class RolNested(BaseModel):
    """
    Esquema simplificado para Rol, útil cuando se anida dentro de otros esquemas
    (ej. en Persona, Usuario) para evitar referencias circulares o datos excesivos.
    Solo incluye los campos esenciales.
    """
    rol_id: int
    nombre_rol: str

    model_config = ConfigDict(from_attributes=True)

# --- Esquema para la asignación de roles a una persona ---
class PersonaRolAsignacion(BaseModel):
    persona_id: int
    rol_id: int

    model_config = ConfigDict(from_attributes=True)