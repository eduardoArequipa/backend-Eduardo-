from sqlalchemy import Column, Integer, String, Text, DateTime, Enum
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func # Para CURRENT_TIMESTAMP

from .base import Base
from .enums import EstadoEnum

class Marca(Base):
    __tablename__ = "marcas"

    marca_id = Column(Integer, primary_key=True, index=True)
    nombre_marca = Column(String(50), unique=True, nullable=False)
    descripcion = Column(Text, nullable=True)
    pais_origen = Column(String(50), nullable=True)
    estado = Column(Enum(EstadoEnum), default=EstadoEnum.activo, nullable=False)
    creado_en = Column(DateTime, default=func.now())

    # Relación inversa con Producto
    productos = relationship("Producto", back_populates="marca")

    def __repr__(self):
        return f"<Marca(marca_id={self.marca_id}, nombre_marca='{self.nombre_marca}')>"