# backend/app/schemas/marca.py
from typing import Optional
from pydantic import BaseModel, ConfigDict
from datetime import datetime

class MarcaBase(BaseModel):
    nombre_marca: str

class MarcaCreate(MarcaBase):
    descripcion: Optional[str] = None
    pais_origen: Optional[str] = None

class Marca(MarcaBase):
    marca_id: int
    descripcion: Optional[str] = None
    pais_origen: Optional[str] = None
    estado: str # 'activo' o 'inactivo'
    creado_en: datetime

    model_config = ConfigDict(from_attributes=True)

class MarcaNested(BaseModel):
    marca_id: int
    nombre_marca: str

    model_config = ConfigDict(from_attributes=True)