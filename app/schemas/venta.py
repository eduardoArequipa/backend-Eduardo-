# backEnd/app/schemas/venta.py
from pydantic import BaseModel
from typing import List, Optional
from decimal import Decimal
from datetime import datetime
from ..schemas.persona import PersonaBase
from ..schemas.metodo_pago import MetodoPago
from ..schemas.usuario import UsuarioAudit
from ..models.enums import EstadoVentaEnum

# Esquema base para Producto (usado en la respuesta de Venta)
class ProductoSchemaBase(BaseModel):
    producto_id: int
    nombre: str
    codigo: str

    class Config:
        from_attributes = True

# Esquema base para DetalleVenta
class DetalleVentaBase(BaseModel):
    producto_id: int
    cantidad: Decimal
    precio_unitario: Decimal
    presentacion_venta: Optional[str] = None

    class Config:
        from_attributes = True

# Esquema para crear un DetalleVenta
class DetalleVentaCreate(DetalleVentaBase):
    pass

# Esquema para leer un DetalleVenta (respuesta)
class DetalleVenta(DetalleVentaBase):
    detalle_id: int
    venta_id: int
    producto: ProductoSchemaBase # Incluir el producto completo

# Esquema base para Venta
class VentaBase(BaseModel):
    persona_id: Optional[int] = None
    metodo_pago_id: int
    estado: EstadoVentaEnum = EstadoVentaEnum.activa

# Esquema para crear una Venta
class VentaCreate(VentaBase):
    detalles: List[DetalleVentaCreate]
    solicitar_factura: bool = False # <-- CAMPO AÑADIDO

# Esquema para la información básica de una factura electrónica anidada
class FacturaElectronicaBase(BaseModel):
    factura_id: int
    cuf: Optional[str] = None
    estado: str

    class Config:
        from_attributes = True


# Esquema para leer una Venta (respuesta)
class Venta(VentaBase):
    venta_id: int
    fecha_venta: datetime
    total: Decimal
    creador: Optional[UsuarioAudit] = None
    modificador: Optional[UsuarioAudit] = None
    
    persona: Optional[PersonaBase] = None
    metodo_pago: MetodoPago
    detalles: List[DetalleVenta] = []
    factura_electronica: Optional[FacturaElectronicaBase] = None

    class Config:
        from_attributes = True

# Esquema para la paginación de Ventas
class VentaPagination(BaseModel):
    items: List[Venta]
    total: int