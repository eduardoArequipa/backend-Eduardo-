# backend/app/schemas/unidad_medida.py
from typing import Optional
from pydantic import BaseModel, ConfigDict
from datetime import datetime

class UnidadMedidaBase(BaseModel):
    nombre_unidad: str
    abreviatura: str
    es_fraccionable: bool = False  # Permite cantidades decimales en ventas (ej: 0.5 metros) 

class UnidadMedidaCreate(UnidadMedidaBase):
    descripcion: Optional[str] = None

class UnidadMedida(UnidadMedidaBase):
    unidad_id: int
    descripcion: Optional[str] = None
    estado: str # 'activo' o 'inactivo'
    creado_en: datetime

    model_config = ConfigDict(from_attributes=True)

class UnidadMedidaNested(BaseModel):
    unidad_id: int
    nombre_unidad: str
    abreviatura: str
    es_fraccionable: bool

    model_config = ConfigDict(from_attributes=True)