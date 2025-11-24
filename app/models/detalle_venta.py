# backEnd/app/models/detalle_venta.py
from sqlalchemy import Column, Integer, DECIMAL, ForeignKey, String
from sqlalchemy.orm import relationship
from .base import Base

class DetalleVenta(Base):
    __tablename__ = "detalle_ventas"
    detalle_id = Column(Integer, primary_key=True, index=True)
    venta_id = Column(Integer, ForeignKey("ventas.venta_id"), nullable=False)
    producto_id = Column(Integer, ForeignKey("productos.producto_id"), nullable=False)
    cantidad = Column(DECIMAL(10, 2), nullable=False)
    precio_unitario = Column(DECIMAL(10, 2), nullable=False)
    presentacion_venta = Column(String(50), nullable=True) # Campo para la unidad de venta (ej: "Caja", "Unidad")

    venta = relationship("Venta", back_populates="detalles")
    producto = relationship("Producto")