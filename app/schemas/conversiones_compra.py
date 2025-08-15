from typing import Optional
from pydantic import BaseModel, ConfigDict
from decimal import Decimal

class ConversionesCompraBase(BaseModel):
    producto_id: int
    nombre_presentacion: str
    unidad_inventario_por_presentacion: Decimal

class ConversionesCompraCreate(ConversionesCompraBase):
    pass

class ConversionesCompraUpdate(BaseModel):
    producto_id: Optional[int] = None
    nombre_presentacion: Optional[str] = None
    unidad_inventario_por_presentacion: Optional[Decimal] = None

class ConversionesCompra(ConversionesCompraBase):
    conversion_id: int

    model_config = ConfigDict(from_attributes=True)
