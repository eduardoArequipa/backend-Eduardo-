# Componente1_SistemaWeb/backEnd/app/models/persona.py

from sqlalchemy import Column, Integer, String, Text, Enum
from sqlalchemy.orm import relationship
from .base import Base
from .enums import EstadoEnum, GeneroEnum # Asumiendo que estos enums están correctamente definidos
from .persona_rol import PersonaRol # Importamos el modelo PersonaRol, no solo el nombre de la tabla de asociación

class Persona(Base):
    __tablename__ = 'personas'

    persona_id = Column(Integer, primary_key=True, index=True)
    nombre = Column(String(100), nullable=False)
    apellido_paterno = Column(String(100))
    apellido_materno = Column(String(100))
    ci = Column(String(20), unique=True)
    genero = Column(Enum(GeneroEnum))
    telefono = Column(String(20))
    email = Column(String(100), unique=True)
    direccion = Column(Text)
    estado = Column(Enum(EstadoEnum), default=EstadoEnum.activo)


    usuario = relationship("Usuario", back_populates="persona", uselist=False, cascade="all, delete")


    proveedor = relationship("Proveedor", back_populates="persona", uselist=False, cascade="all, delete")


    ventas = relationship("Venta", back_populates="persona")

    # Nueva Relación Muchos-a-Muchos con Rol a través del modelo de asociación PersonaRol
    # Usamos 'PersonaRol.__table__' como el argumento 'secondary' para indicar la tabla intermedia.
    roles = relationship(
            "Rol",
            secondary=PersonaRol.__tablename__,
            back_populates="personas",
            overlaps="persona_roles,rol,persona" # Soluciona advertencias relacionadas con Persona.roles
        )
    # Relación uno-a-muchos con los objetos de asociación PersonaRol directamente
    # Útil si necesitas acceder a los atributos adicionales que podría tener la tabla de unión en el futuro.
    persona_roles = relationship(
        "PersonaRol",
        back_populates="persona",
        overlaps="roles", # Soluciona advertencias relacionadas con Persona.persona_roles
        cascade="all, delete-orphan" # Mantener cascade para la limpieza de la tabla de unión
    )
    def __repr__(self):
        return f"<Persona(id={self.persona_id}, nombre='{self.nombre} {self.apellido_paterno}')>"