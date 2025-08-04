from sqlalchemy import Column, Integer, String, DECIMAL, TIMESTAMP, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime
from .base import Base
from .enums import EstadoVentaEnum

class Venta(Base):
    __tablename__ = "ventas"
    venta_id = Column(Integer, primary_key=True, index=True)
    persona_id = Column(Integer, ForeignKey("personas.persona_id"), nullable=True) # Ahora se relaciona con Persona
    fecha_venta = Column(TIMESTAMP, default=datetime.now)
    total = Column(DECIMAL(10, 2), nullable=False)
    metodo_pago_id = Column(Integer, ForeignKey("metodos_pago.metodo_pago_id"), nullable=False)
    estado = Column(String(20), default=EstadoVentaEnum.activa.value, nullable=False)
    creado_por = Column(Integer, ForeignKey("usuarios.usuario_id"), nullable=True)
    modificado_por = Column(Integer, ForeignKey("usuarios.usuario_id"), nullable=True)

    detalles = relationship("DetalleVenta", back_populates="venta", cascade="all, delete-orphan")
    persona = relationship("Persona") # Nueva relación con Persona
    metodo_pago = relationship("MetodoPago", back_populates="ventas")
    creador = relationship("Usuario", foreign_keys=[creado_por])
    modificador = relationship("Usuario", foreign_keys=[modificado_por])

 