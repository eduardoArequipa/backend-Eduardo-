# backEnd/app/schemas/rol.py

from pydantic import BaseModel, Field, ConfigDict
from typing import Optional
from ..models.enums import EstadoEnum # Asumiendo que EstadoEnum es el correcto para el estado del rol

# --- Esquema base para Rol ---
class RolBase(BaseModel):
    rol_id: Optional[int] = None # El ID será opcional al crear, pero requerido al leer
    nombre_rol: str = Field(..., min_length=3, max_length=50, description="Nombre único del rol")
    descripcion: Optional[str] = Field(None, description="Descripción detallada del rol")
    # El estado se define aquí como un campo opcional con un valor por defecto para la creación
    estado: Optional[EstadoEnum] = EstadoEnum.activo # <-- ¡CAMBIO AQUÍ! (Añadido estado a RolBase)

# --- Esquema para crear un Rol ---
class RolCreate(RolBase):
    """Esquema para crear un nuevo Rol."""
    pass # Hereda todos los campos de RolBase

# --- Esquema para actualizar un Rol ---
class RolUpdate(BaseModel):
    """
    Esquema para actualizar los datos de un Rol.
    Todos los campos son opcionales para permitir actualizaciones parciales.
    """
    nombre_rol: Optional[str] = Field(None, min_length=3, max_length=50)
    descripcion: Optional[str] = None
    estado: Optional[EstadoEnum] = None # Permitir cambiar el estado del rol

# --- Esquema para representar un Rol leído de la base de datos ---
class RolInDB(RolBase): # <-- ¡CAMBIO DE NOMBRE! (Antes Rol)
    """
    Esquema para representar un Rol tal como se lee de la base de datos,
    incluyendo su ID. Este es el esquema completo del Rol.
    """
    rol_id: int # El ID generado por la base de datos

    model_config = ConfigDict(from_attributes=True) # Configuración para mapear desde modelos ORM (Pydantic v2.x)

# --- Esquema simplificado para Rol (anidado) ---
class RolNested(BaseModel): # <-- ¡CAMBIO DE NOMBRE! (Antes RolNested, pero ahora es más claro)
    """
    Esquema simplificado para Rol, útil cuando se anida dentro de otros esquemas
    (ej. en Persona, Usuario) para evitar referencias circulares o datos excesivos.
    Solo incluye los campos esenciales.
    """
    rol_id: int
    nombre_rol: str

    model_config = ConfigDict(from_attributes=True)