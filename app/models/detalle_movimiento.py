from sqlalchemy import Column, Integer, Numeric, ForeignKey
from sqlalchemy.orm import relationship
from .base import Base

class DetalleMovimientoInventario(Base):
    __tablename__ = 'detalle_movimientos_inventario'

    id = Column(Integer, primary_key=True, index=True)
    
    movimiento_id = Column(Integer, ForeignKey('movimientos_inventario.movimiento_id', ondelete="CASCADE"), nullable=False)
    
    # conversion_id es opcional/nullable porque una de las líneas del detalle puede ser la unidad base,
    # que no tiene una entrada en la tabla de conversiones.
    conversion_id = Column(Integer, ForeignKey('conversiones.id'), nullable=True)
    
    # La cantidad para esta línea de detalle específica (ej. cantidad de 'cajas' o 'metros')
    cantidad = Column(Numeric(10, 2), nullable=False)

    # Relaciones
    movimiento = relationship("MovimientoInventario", back_populates="detalles")
    conversion = relationship("Conversion")
