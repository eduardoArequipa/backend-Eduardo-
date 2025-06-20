# backEnd/app/schemas/rol.py
from pydantic import BaseModel, Field, ConfigDict
from typing import Optional
from datetime import datetime
from ..models.enums import EstadoEnum 

class RolBase(BaseModel):
    nombre_rol: str = Field(..., min_length=1, max_length=50)
    descripcion: str = Field(..., min_length=1)
    estado: Optional[EstadoEnum] = EstadoEnum.activo 

class RolCreate(RolBase):
    nombre_rol: str = Field(..., min_length=1, max_length=50) 
    descripcion: str = Field(..., min_length=1) 


class RolUpdate(RolBase):
     pass

class Rol(RolBase):
    rol_id: int

    model_config = ConfigDict(from_attributes=True)

class RolNested(Rol):
    model_config = ConfigDict(from_attributes=True)
