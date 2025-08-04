# backEnd/app/models/detalle_venta.py (Ejemplo, puede que ya lo tengas)
from sqlalchemy import Column, Integer, DECIMAL, ForeignKey
from sqlalchemy.orm import relationship
from .base import Base
from decimal import Decimal
class DetalleVenta(Base):
    __tablename__ = "detalle_ventas"
    detalle_id = Column(Integer, primary_key=True, index=True)
    venta_id = Column(Integer, ForeignKey("ventas.venta_id", ondelete="CASCADE"), nullable=False)
    producto_id = Column(Integer, ForeignKey("productos.producto_id"), nullable=False)
    cantidad = Column(DECIMAL(10, 2), nullable=False)  # Cambiado a DECIMAL para soportar metros
    precio_unitario = Column(DECIMAL(10, 2), nullable=False)

    venta = relationship("Venta", back_populates="detalles")
    producto = relationship("Producto")

    @property
    def subtotal(self) -> Decimal:
        """Calcula el subtotal multiplicando cantidad por precio_unitario."""
        if self.cantidad is not None and self.precio_unitario is not None:
            return Decimal(self.cantidad) * Decimal(self.precio_unitario)
        return Decimal("0.00")
