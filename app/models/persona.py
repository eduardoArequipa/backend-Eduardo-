# backEnd/app/models/persona.py
from sqlalchemy import Column, Integer, String, Text, DateTime, Enum
from sqlalchemy.orm import relationship
from .base import Base
from .enums import EstadoEnum, GeneroEnum # Importamos los Enums
from datetime import datetime

class Persona(Base):
    __tablename__ = 'personas'

    persona_id = Column(Integer, primary_key=True, index=True)
    nombre = Column(String(100), nullable=False)
    apellido_paterno = Column(String(100))
    apellido_materno = Column(String(100))
    ci = Column(String(20), unique=True)
    genero = Column(Enum(GeneroEnum)) # Usamos el Enum
    telefono = Column(String(20))
    email = Column(String(100), unique=True)
    direccion = Column(Text)
    estado = Column(Enum(EstadoEnum), default=EstadoEnum.activo) # Usamos el Enum

    
    usuario = relationship("Usuario", back_populates="persona", uselist=False)
    proveedor = relationship("Proveedor", back_populates="persona", uselist=False) # uselist=False para 1:1
    cliente = relationship("Cliente", back_populates="persona", uselist=False)

    # Puedes agregar relaciones a Cliente, Proveedor si tuvieras esas tablas específicas
    # cliente = relationship("Cliente", back_populates="persona", uselist=False)
    # proveedor = relationship("Proveedor", back_populates="persona", uselist=False)

    def __repr__(self):
        return f"<Persona(id={self.persona_id}, nombre='{self.nombre} {self.apellido_paterno}')>"