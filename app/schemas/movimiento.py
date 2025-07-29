from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional

from .producto import Producto as ProductoSchema
from .usuario import Usuario as UsuarioSchema

class MovimientoBase(BaseModel):
    producto_id: int
    tipo_movimiento: str = Field(..., description="Tipo de movimiento (merma, ajuste_positivo, ajuste_negativo, uso_interno)")
    cantidad: float = Field(..., gt=0, description="Cantidad del producto movido")
    motivo: Optional[str] = Field(None, description="Motivo del movimiento")

class MovimientoCreate(MovimientoBase):
    pass

class MovimientoResponse(MovimientoBase):
    movimiento_id: int
    usuario_id: int
    stock_anterior: int
    stock_nuevo: int
    fecha_movimiento: datetime

    producto: ProductoSchema
    usuario: UsuarioSchema

    class Config:
        from_attributes = True