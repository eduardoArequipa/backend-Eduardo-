from sqlalchemy import Column, Integer, String, Boolean, Text, DateTime
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func # Para CURRENT_TIMESTAMP

from .base import Base

class UnidadMedida(Base):
    __tablename__ = "unidades_medida"

    unidad_id = Column(Integer, primary_key=True, index=True)
    nombre_unidad = Column(String(20), unique=True, nullable=False)
    abreviatura = Column(String(5), nullable=False)
    es_fraccionable = Column(Boolean, default=False)
    descripcion = Column(Text, nullable=True)
    estado = Column(String(20), default='activo') # O puedes usar un Enum si lo tienes para estados generales
    creado_en = Column(DateTime, default=func.now())

    # Relación inversa con Producto
    productos = relationship("Producto", back_populates="unidad_inventario")

    def __repr__(self):
        return f"<UnidadMedida(unidad_id={self.unidad_id}, nombre_unidad='{self.nombre_unidad}', abreviatura='{self.abreviatura}')>"