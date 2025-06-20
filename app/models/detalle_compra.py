# backEnd/app/models/detalle_compra.py
from sqlalchemy import Column, Integer, ForeignKey, DECIMAL
from sqlalchemy.orm import relationship

from .base import Base # Importa la base declarativa
# Importa los modelos relacionados para definir las relaciones
from .compra import Compra
from .producto import Producto


# Nota: Este modelo mapea la tabla detalle_compras.

class DetalleCompra(Base):
    __tablename__ = "detalle_compras" # Mapea a la tabla 'detalle_compras' en la base de datos

    detalle_id = Column(Integer, primary_key=True, index=True) # Clave primaria

    # Claves Foráneas a Compra y Producto
    compra_id = Column(Integer, ForeignKey('compras.compra_id', ondelete='CASCADE'), nullable=False) # ondelete='CASCADE' para eliminar detalles si se elimina la compra
    producto_id = Column(Integer, ForeignKey('productos.producto_id'), nullable=False)

    cantidad = Column(Integer, nullable=False) # Cantidad del producto en esta línea de detalle
    precio_unitario = Column(DECIMAL(10, 2), nullable=False) # Precio por unidad en esta compra específica

    # Definir relaciones ORM
    # Relación N:1 con Compra
    compra = relationship("Compra", back_populates="detalles")

    # Relación N:1 con Producto
    producto = relationship("Producto", back_populates="detalle_compras") # Asumiendo que la relación inversa en Producto se llama detalle_compras


    # El método __repr__ es útil para la depuración
    def __repr__(self):
        return f"<DetalleCompra(detalle_id={self.detalle_id}, compra_id={self.compra_id}, producto_id={self.producto_id}, cantidad={self.cantidad}, precio_unitario={self.precio_unitario})>"

