# Componente1_SistemaWeb/backEnd/app/models/persona_rol.py

from sqlalchemy import Column, Integer, ForeignKey
from sqlalchemy.orm import relationship
from .base import Base

class PersonaRol(Base):
    """
    Modelo SQLAlchemy para la tabla de asociación 'persona_roles'.
    Define la relación muchos-a-muchos entre Personas y Roles.
    """
    __tablename__ = 'persona_roles'

    persona_id = Column(Integer, ForeignKey('personas.persona_id', ondelete='CASCADE'), nullable=False, primary_key=True)
    rol_id = Column(Integer, ForeignKey('roles.rol_id', ondelete='CASCADE'), nullable=False, primary_key=True)


    persona = relationship("Persona", back_populates="persona_roles")
    rol = relationship("Rol", back_populates="persona_roles")

    def __repr__(self):
        """Representación string del objeto PersonaRol."""
        return f"<PersonaRol(persona_id={self.persona_id}, rol_id={self.rol_id})>"