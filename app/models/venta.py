from sqlalchemy import Column, Integer, String, DECIMAL, TIMESTAMP, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime
from .base import Base
from .enums import EstadoVentaEnum # Asegúrate de que este Enum exista

class Venta(Base):
    __tablename__ = "ventas"
    venta_id = Column(Integer, primary_key=True, index=True)
    cliente_id = Column(Integer, ForeignKey("clientes.cliente_id")) # Puede ser nulo para ventas sin cliente registrado
    fecha_venta = Column(TIMESTAMP, default=datetime.now)
    total = Column(DECIMAL(10,2), nullable=False)
    metodo_pago_id = Column(Integer, ForeignKey("metodos_pago.metodo_pago_id"), nullable=False)
    estado = Column(String(20), default=EstadoVentaEnum.activa.value, nullable=False) # Usa el Enum
    creado_por = Column(Integer, ForeignKey("usuarios.usuario_id"), nullable=True)
    modificado_por = Column(Integer, ForeignKey("usuarios.usuario_id"), nullable=True)

    detalles = relationship("DetalleVenta", back_populates="venta", cascade="all, delete-orphan")
    cliente = relationship("Cliente", back_populates="ventas")
    metodo_pago = relationship("MetodoPago", back_populates="ventas")
    creador = relationship("Usuario", foreign_keys=[creado_por])
    modificador = relationship("Usuario", foreign_keys=[modificado_por])