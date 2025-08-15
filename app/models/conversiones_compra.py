from sqlalchemy import Column, Integer, String, Numeric, ForeignKey
from sqlalchemy.orm import relationship
from .base import Base

class ConversionesCompra(Base):
    __tablename__ = 'conversiones_compra'

    conversion_id = Column(Integer, primary_key=True, index=True)
    producto_id = Column(Integer, ForeignKey('productos.producto_id', ondelete='CASCADE'), nullable=False)
    nombre_presentacion = Column(String(50), nullable=False)
    unidad_inventario_por_presentacion = Column(Numeric(10, 2), nullable=False)

    # Relación inversa con Producto
    producto = relationship("Producto", back_populates="conversiones")
