from sqlalchemy import Column, Integer, String, Text, Numeric, TIMESTAMP, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from .base import Base

class MovimientoInventario(Base):
    __tablename__ = 'movimientos_inventario'

    movimiento_id = Column(Integer, primary_key=True, index=True)
    producto_id = Column(Integer, ForeignKey('productos.producto_id'), nullable=False)
    usuario_id = Column(Integer, ForeignKey('usuarios.usuario_id'), nullable=False)
    tipo_movimiento = Column(String(20), nullable=False)
    cantidad = Column(Numeric(10, 3), nullable=False)
    motivo = Column(Text)
    stock_anterior = Column(Integer, nullable=False)
    stock_nuevo = Column(Integer, nullable=False)
    fecha_movimiento = Column(TIMESTAMP(timezone=True), server_default=func.now())

    # Relaciones para acceder a los objetos completos de Producto y Usuario
    producto = relationship("Producto")
    usuario = relationship("Usuario")
