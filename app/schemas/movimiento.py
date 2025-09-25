from pydantic import BaseModel, Field, validator
from datetime import datetime
from typing import Optional
from decimal import Decimal

from .producto import Producto as ProductoSchema
from .usuario import Usuario as UsuarioSchema
from ..models.enums import TipoMovimientoEnum

class MovimientoBase(BaseModel):
    producto_id: int
    tipo_movimiento: TipoMovimientoEnum = Field(..., description="Tipo de movimiento")
    cantidad: Decimal = Field(..., gt=0, description="Cantidad del producto movido")
    motivo: Optional[str] = Field(None, description="Motivo del movimiento")

    @validator('cantidad')
    def validate_cantidad_positiva(cls, v):
        if v <= 0:
            raise ValueError('La cantidad debe ser mayor a cero')
        return v

class MovimientoCreate(MovimientoBase):
    pass

class MovimientoResponse(MovimientoBase):
    movimiento_id: int
    usuario_id: int
    stock_anterior: Decimal
    stock_nuevo: Decimal
    fecha_movimiento: datetime

    producto: ProductoSchema
    usuario: UsuarioSchema

    class Config:
        from_attributes = True

# Esquema para la paginación de Movimientos
class MovimientoPagination(BaseModel):
    items: list[MovimientoResponse]
    total: int