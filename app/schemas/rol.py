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
    # backEnd/app/schemas/rol.py

from pydantic import BaseModel, Field, ConfigDict
from typing import Optional, List
from ..models.enums import EstadoEnum
from .menu import MenuInDB # <-- ¡CAMBIO AQUÍ! Importamos el schema de Menu

# --- Esquema base para Rol ---
class RolBase(BaseModel):
    rol_id: Optional[int] = None
    nombre_rol: str = Field(..., min_length=3, max_length=50, description="Nombre único del rol")
    descripcion: Optional[str] = Field(None, description="Descripción detallada del rol")
    estado: Optional[EstadoEnum] = EstadoEnum.activo

# --- Esquema para crear un Rol (ya no se usará en la API, pero se puede mantener para tests) ---
class RolCreate(RolBase):
    pass

# --- Esquema para actualizar un Rol (ya no se usará en la API) ---
class RolUpdate(BaseModel):
    nombre_rol: Optional[str] = Field(None, min_length=3, max_length=50)
    descripcion: Optional[str] = None
    estado: Optional[EstadoEnum] = None

# --- Esquema para representar un Rol leído de la base de datos ---
class RolInDB(RolBase):
    rol_id: int
    menus: List[MenuInDB] = [] # Asegura que el campo siempre exista

    model_config = ConfigDict(from_attributes=True, arbitrary_types_allowed=True)

# --- Esquema simplificado para Rol (anidado) ---
class RolNested(BaseModel):
    rol_id: int
    nombre_rol: str

    model_config = ConfigDict(from_attributes=True)

# --- Esquema para la asignación de roles a una persona ---
class PersonaRolAsignacion(BaseModel):
    persona_id: int
    rol_id: int

    model_config = ConfigDict(from_attributes=True)


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

class RolInDB(BaseModel):
    rol_id: int
    nombre_rol: str
    descripcion: Optional[str] = None
    estado: str
    menus: List[MenuInDB] = []  # Lista vacía por defecto
    
    class Config:
        from_attributes = True  # Para SQLAlchemy ORM
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