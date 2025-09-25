# backend/app/schemas/marca.py
from typing import Optional, List
from pydantic import BaseModel, ConfigDict, Field
from datetime import datetime
from ..models.enums import EstadoEnum

class MarcaBase(BaseModel):
    nombre_marca: str = Field(..., min_length=2, max_length=50, description="Nombre de la marca")

class MarcaCreate(MarcaBase):
    descripcion: Optional[str] = Field(None, max_length=500, description="Descripción de la marca")
    pais_origen: Optional[str] = Field(None, max_length=50, description="País de origen de la marca")

class Marca(MarcaBase):
    marca_id: int
    descripcion: Optional[str] = None
    pais_origen: Optional[str] = None
    estado: EstadoEnum
    creado_en: datetime

    model_config = ConfigDict(from_attributes=True)

class MarcaNested(BaseModel):
    marca_id: int
    nombre_marca: str

    model_config = ConfigDict(from_attributes=True)

# Esquema para la paginación de Marcas
class MarcaPagination(BaseModel):
    items: List[Marca]
    total: int