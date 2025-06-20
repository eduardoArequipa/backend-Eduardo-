# backEnd/app/models/rol.py
from sqlalchemy import Column, Integer, String, Text, DateTime, Enum
from sqlalchemy.orm import relationship
from .base import Base
from .enums import EstadoEnum # Importamos el Enum
from datetime import datetime

class Rol(Base):
    __tablename__ = 'roles'

    rol_id = Column(Integer, primary_key=True, index=True)
    nombre_rol = Column(String(50), unique=True, nullable=False)
    descripcion = Column(Text, nullable=False)
    estado = Column(Enum(EstadoEnum), default=EstadoEnum.activo) # Usamos el Enum


    usuarios = relationship("Usuario", secondary="usuario_roles", back_populates="roles")

    def __repr__(self):
        return f"<Rol(id={self.rol_id}, nombre='{self.nombre_rol}')>"