# Componente1_SistemaWeb/backEnd/app/models/rol.py

from sqlalchemy import Column, Integer, String, Text, Enum
from sqlalchemy.orm import relationship
from .base import Base
from .enums import EstadoEnum 
from .persona_rol import PersonaRol 

class Rol(Base):
    __tablename__ = 'roles'

    rol_id = Column(Integer, primary_key=True, index=True)
    nombre_rol = Column(String(50), unique=True, nullable=False)
    descripcion = Column(Text, nullable=False)
    estado = Column(Enum(EstadoEnum), default='activo') 


    personas = relationship(
        "Persona",
        secondary=PersonaRol.__tablename__,
        back_populates="roles",
        overlaps="persona_roles,persona,rol"
    )
    persona_roles = relationship(
        "PersonaRol",
        back_populates="rol",
        overlaps="personas", # Soluciona advertencias relacionadas con Rol.persona_roles
        cascade="all, delete-orphan" # Añadido cascade para la limpieza de la tabla de unión
    )

    # Nueva relación con Menus (muchos a muchos)
    rol_menus = relationship(
        "RolMenu",
        back_populates="rol",
        cascade="all, delete-orphan"
    )
    
    # Acceso directo a los menús a través de la tabla de asociación
    menus = relationship(
        "Menu",
        secondary="rol_menus",
        back_populates="roles",
        overlaps="rol_menus"
    )

    def __repr__(self):
        return f"<Rol(id={self.rol_id}, nombre_rol='{self.nombre_rol}')>"