# backEnd/app/models/detalle_compra.py
from sqlalchemy import Column, Integer, Float, ForeignKey, String, DECIMAL
from sqlalchemy.orm import relationship
from .base import Base

class DetalleCompra(Base):
    __tablename__ = 'detalle_compras'

    detalle_id = Column(Integer, primary_key=True, index=True)
    compra_id = Column(Integer, ForeignKey('compras.compra_id', ondelete='CASCADE'))
    producto_id = Column(Integer, ForeignKey('productos.producto_id'))
    cantidad = Column(DECIMAL(10, 2), nullable=False)
    precio_unitario = Column(Float, nullable=False)
    presentacion_compra = Column(String(50), nullable=True) # Nuevo campo
    
    # Relaciones
    producto = relationship("Producto")
    compra = relationship("Compra", back_populates="detalles")


    # El método __repr__ es útil para la depuración
    def __repr__(self):
        return f"<DetalleCompra(detalle_id={self.detalle_id}, compra_id={self.compra_id}, producto_id={self.producto_id}, cantidad={self.cantidad}, precio_unitario={self.precio_unitario})>"

