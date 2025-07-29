# backEnd/app/models/detalle_venta.py (Ejemplo, puede que ya lo tengas)
from sqlalchemy import Column, Integer, DECIMAL, ForeignKey
from sqlalchemy.orm import relationship
from .base import Base

class DetalleVenta(Base):
    __tablename__ = "detalle_ventas"
    detalle_id = Column(Integer, primary_key=True, index=True)
    venta_id = Column(Integer, ForeignKey("ventas.venta_id", ondelete="CASCADE"), nullable=False)
    producto_id = Column(Integer, ForeignKey("productos.producto_id"), nullable=False)
    cantidad = Column(Integer, nullable=False)
    precio_unitario = Column(DECIMAL(10,2), nullable=False)

    venta = relationship("Venta", back_populates="detalles")
    producto = relationship("Producto")


    @property
    def subtotal(self) -> float: # O Decimal, dependiendo de tu precisión deseada
        """Calcula el subtotal multiplicando cantidad por precio_unitario."""
        if self.cantidad is not None and self.precio_unitario is not None:
            # Asegúrate de convertir a float o Decimal antes de multiplicar
            # para evitar problemas de tipo si vienen como objetos Decimal de SQLAlchemy.
            return float(self.cantidad) * float(self.precio_unitario)
        return 0.0 # Valor por defecto si cantidad o precio_unitario son nulos/incorrectos
