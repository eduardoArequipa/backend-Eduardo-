# backEnd/app/models/metodo_pago.py
from sqlalchemy import Column, Integer, String
from sqlalchemy.orm import relationship
from .base import Base # Asegúrate de que esta ruta sea correcta
from .enums import EstadoEnum # Asume que tienes un Enum para el estado (activo/inactivo)

class MetodoPago(Base):
    __tablename__ = "metodos_pago"
    metodo_pago_id = Column(Integer, primary_key=True, index=True)
    nombre_metodo = Column(String(50), unique=True, nullable=False)
    estado = Column(String(20), default=EstadoEnum.activo.value, nullable=False) # Usa el Enum

    # Relación de vuelta para Ventas
    ventas = relationship("Venta", back_populates="metodo_pago")