# backEnd/app/models/cliente.py
from sqlalchemy import Column, Integer, String, ForeignKey
from sqlalchemy.orm import relationship
from .base import Base # Asegúrate de que esta ruta sea correcta
from .persona import Persona # Asume que tienes este modelo en models/persona.py
from .enums import EstadoEnum # Asume que tienes un Enum para el estado (activo/inactivo)

class Cliente(Base):
    __tablename__ = "clientes"
    cliente_id = Column(Integer, primary_key=True, index=True)
    persona_id = Column(Integer, ForeignKey("personas.persona_id"), unique=True, nullable=False)
    estado = Column(String(20), default=EstadoEnum.activo.value, nullable=False) # Usa el Enum

    # Relaciones
    persona = relationship("Persona", back_populates="cliente", uselist=False) # Cliente tiene una relación 1 a 1 con Persona
    ventas = relationship("Venta", back_populates="cliente") # Un cliente puede tener muchas ventas