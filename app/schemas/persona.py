import re
from pydantic import BaseModel, Field, EmailStr, ConfigDict, validator
from typing import Optional, List
from ..models.enums import EstadoEnum, GeneroEnum
from .rol import RolBase, RolInDB
from .pagination import Pagination # Importar la clase Pagination

# --- Esquema para anidar datos de Usuario en la creación de Persona ---
class UsuarioCreateSchemaForPersona(BaseModel):
    nombre_usuario: str = Field(..., min_length=1, max_length=50, description="Nombre de usuario para el acceso al sistema")
    contraseña: str = Field(..., min_length=6, description="Contraseña para el usuario")
    estado: Optional[EstadoEnum] = EstadoEnum.activo
    foto_ruta: Optional[str] = None

# --- Esquema Base para Persona ---
# Contiene todos los campos y validaciones. Los campos que pueden ser nulos en la BD son Opcionales.
class PersonaBase(BaseModel):
    nombre: str = Field(..., min_length=3, max_length=100, description="El nombre debe tener al menos 3 caracteres.")
    apellido_paterno: Optional[str] = Field(None, min_length=3, max_length=100, description="El apellido paterno debe tener al menos 3 caracteres.")
    apellido_materno: Optional[str] = Field(None, min_length=3, max_length=100, description="El apellido materno debe tener al menos 3 caracteres.")
    ci: str = Field(None, max_length=20, description="Cédula de Identidad, debe ser única y solo contener números.")
    genero: Optional[GeneroEnum] = None
    telefono: Optional[str] = Field(None, max_length=20, description="El teléfono debe tener solo números y puede incluir el prefijo de país.")
    email: Optional[EmailStr] = Field(None, max_length=100, description="Dirección de correo electrónico, debe ser única.")
    direccion: Optional[str] = Field(None, max_length=255)
    estado: Optional[EstadoEnum] = EstadoEnum.activo
    roles: List[RolBase] = []

    @validator('nombre', 'apellido_paterno', 'apellido_materno')
    def validate_string_fields(cls, v):
        if v is not None and not v.strip():
            raise ValueError("El campo no puede estar vacío.")
        return v


    @validator('telefono')
    def validate_telefono(cls, v):
        # Permite el formato internacional (ej. +591) y números simples.
        if v and not re.match(r'^\+?[0-9]+$', v):
            raise ValueError("El teléfono solo debe contener números y opcionalmente un '+' al inicio.")
        return v

# --- Esquema para crear una Persona ---
# Hereda de PersonaBase y hace obligatorios los campos requeridos para nuevos registros.
class PersonaCreate(PersonaBase):
    ci: str = Field(..., max_length=20, description="Cédula de Identidad, debe ser única y solo contener números.")
    telefono: str = Field(..., max_length=20, description="El teléfono debe tener solo números y puede incluir el prefijo de país.")
    email: EmailStr = Field(..., max_length=100, description="Dirección de correo electrónico, debe ser única.")

    rol_ids: Optional[List[int]] = Field(default_factory=list, description="Lista de IDs de roles a asignar a la persona.")
    usuario_data: Optional[UsuarioCreateSchemaForPersona] = Field(None, description="Datos para crear un Usuario asociado.")

# --- Esquema para actualizar una Persona ---
# Hereda de PersonaBase y hace obligatorios los campos requeridos para nuevos registros.
class PersonaUpdate(PersonaBase):
    nombre: Optional[str] = Field(None, min_length=3, max_length=100)
    apellido_paterno: Optional[str] = Field(None, min_length=3, max_length=100)
    apellido_materno: Optional[str] = Field(None, min_length=3, max_length=100)
    ci: Optional[str] = Field(None, max_length=20)
    genero: Optional[GeneroEnum] = None
    telefono: Optional[str] = Field(None, max_length=20)
    email: Optional[EmailStr] = Field(None, max_length=100)
    direccion: Optional[str] = Field(None)
    estado: Optional[EstadoEnum] = None
    rol_ids: Optional[List[int]] = Field(None, description="Lista completa de IDs de roles para reemplazar los existentes.")

# --- Esquemas para la lectura de Persona desde la DB ---
# Se usa para las respuestas de la API.
class PersonaInDB(PersonaBase):
    persona_id: int
    model_config = ConfigDict(from_attributes=True)

class PersonaWithRoles(PersonaInDB):
    roles: List[RolInDB] = []
    model_config = ConfigDict(from_attributes=True)

class PersonaNested(PersonaInDB):
    """Esquema simplificado para anidar en otras respuestas."""
    pass

# --- Esquema para la respuesta de paginación ---
class PersonaPagination(Pagination[PersonaWithRoles]):
    """Esquema para la respuesta paginada de personas."""
    pass
