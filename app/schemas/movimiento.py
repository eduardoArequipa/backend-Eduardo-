from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional, List
from decimal import Decimal

from .producto import Producto as ProductoSchema
from .usuario import Usuario as UsuarioSchema
from ..models.enums import TipoMovimientoEnum

# Esquema para un item individual en la creación de un movimiento
class MovimientoItem(BaseModel):
    cantidad: Decimal = Field(..., gt=0, description="Cantidad para esta presentación específica")
    conversion_id: Optional[int] = Field(None, description="ID de la conversión de la presentación (nulo si es la unidad base)")

# Esquema base con campos comunes
class MovimientoBase(BaseModel):
    producto_id: int
    tipo_movimiento: TipoMovimientoEnum = Field(..., description="Tipo de movimiento")
    motivo: Optional[str] = Field(None, description="Motivo del movimiento")

# Esquema para la creación de un movimiento
class MovimientoCreate(MovimientoBase):
    items: List[MovimientoItem] = Field(..., min_length=1, description="Lista de items/presentaciones que componen el movimiento")

# --- Esquemas para la respuesta ---

# Esquema anidado para la conversión en la respuesta del detalle
class ConversionNested(BaseModel):
    nombre_presentacion: str
    class Config:
        from_attributes = True

# Esquema para el detalle del movimiento en la respuesta
class DetalleMovimientoResponse(BaseModel):
    cantidad: Decimal
    conversion: Optional[ConversionNested] = None
    class Config:
        from_attributes = True

# Esquema principal para la respuesta de un movimiento
class MovimientoResponse(MovimientoBase):
    movimiento_id: int
    usuario_id: int
    cantidad: Decimal # La cantidad total calculada en la unidad base
    stock_anterior: Decimal
    stock_nuevo: Decimal
    fecha_movimiento: datetime

    producto: ProductoSchema
    usuario: UsuarioSchema
    detalles: List[DetalleMovimientoResponse] = []

    class Config:
        from_attributes = True

# Esquema para la paginación de Movimientos
class MovimientoPagination(BaseModel):
    items: list[MovimientoResponse]
    total: int