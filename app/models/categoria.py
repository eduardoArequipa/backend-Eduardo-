from sqlalchemy import Column, Integer, String, Enum
from .base import Base
from app.models.enums import  EstadoEnum
from sqlalchemy.orm import relationship
from sqlalchemy import TIMESTAMP

class Categoria(Base):
    __tablename__ = "categorias"
    
    categoria_id = Column(Integer, primary_key=True, index=True)
    nombre_categoria= Column(String(50), unique=True)
    estado = Column(Enum(EstadoEnum), default=EstadoEnum.activo)
    # El método __repr__ es útil para la depuración
    def __repr__(self):
        return f"<Categoria(categoria_id={self.categoria_id}, nombre_categoria='{self.nombre_categoria}', estado='{self.estado}')>"
    
    productos = relationship("Producto", back_populates="categoria")
