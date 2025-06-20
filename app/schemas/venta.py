from typing import List, Optional
from datetime import datetime
from decimal import Decimal
from pydantic import BaseModel, Field
from ..models.enums import EstadoVentaEnum

from .usuario import UsuarioAudit
from .cliente import ClienteNested 
from .metodo_pago import MetodoPagoNested 


class ProductoSchemaBase(BaseModel):
    producto_id: int
    codigo: str = Field(..., description="Código único del producto (para escáner)")
    nombre: str
    precio_venta: Decimal = Field(..., gt=0, decimal_places=2, description="Precio actual de venta del producto")
    stock: int = Field(..., ge=0, description="Cantidad en stock del producto")


    class Config:
        from_attributes = True

class DetalleVentaBase(BaseModel):
    producto_id: int = Field(..., description="ID del producto vendido")
    cantidad: int = Field(..., gt=0, description="Cantidad del producto vendido (debe ser mayor a 0)")
    precio_unitario: Decimal = Field(..., gt=0, decimal_places=2, description="Precio unitario al momento de la venta (debe ser mayor a 0)")

class DetalleVentaCreate(DetalleVentaBase):
    """Esquema para crear un detalle de venta."""
    pass

class DetalleVenta(DetalleVentaBase):
    """Esquema para leer un detalle de venta, con ID y producto anidado."""
    detalle_id: int
    producto: ProductoSchemaBase 

    class Config:
        from_attributes = True

class VentaBase(BaseModel):
    cliente_id: Optional[int] = Field(None, description="ID del cliente asociado a la venta (opcional)")
    metodo_pago_id: int = Field(..., description="ID del método de pago utilizado")
    estado: EstadoVentaEnum = Field(EstadoVentaEnum.activa, description="Estado de la venta (activa, anulada)")

class VentaCreate(VentaBase):
    """Esquema para crear una nueva venta, incluye los detalles anidados."""
    detalles: List[DetalleVentaCreate] = Field(..., min_length=1, description="Lista de detalles de la venta (al menos uno)")

class VentaUpdate(BaseModel):
    """Esquema para actualizar el estado de una venta (o campos limitados)."""
    estado: Optional[EstadoVentaEnum] = Field(None, description="Nuevo estado de la venta")
 
class Venta(VentaBase):
    """Esquema para leer una venta completa, incluyendo ID, fechas, total y relaciones."""
    venta_id: int
    fecha_venta: datetime
    total: Decimal = Field(..., decimal_places=2)
    
    cliente: Optional[ClienteNested]
    metodo_pago: MetodoPagoNested 
    detalles: List[DetalleVenta]
    creador: Optional[UsuarioAudit]
    modificador: Optional[UsuarioAudit]

    class Config:
        from_attributes = True