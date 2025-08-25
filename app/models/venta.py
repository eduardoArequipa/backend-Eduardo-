from sqlalchemy import Column, Integer, String, DECIMAL, TIMESTAMP, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime
from .base import Base
from .enums import EstadoVentaEnum
# Importar el modelo de FacturaElectronica para la relación
from .factura_electronica import FacturaElectronica

class Venta(Base):
    __tablename__ = "ventas"
    venta_id = Column(Integer, primary_key=True, index=True)
    persona_id = Column(Integer, ForeignKey("personas.persona_id"), nullable=True)
    fecha_venta = Column(TIMESTAMP, default=datetime.now)
    total = Column(DECIMAL(10, 2), nullable=False)
    metodo_pago_id = Column(Integer, ForeignKey("metodos_pago.metodo_pago_id"), nullable=False)
    estado = Column(String(20), default=EstadoVentaEnum.activa.value, nullable=False)
    creado_por = Column(Integer, ForeignKey("usuarios.usuario_id"), nullable=True)
    modificado_por = Column(Integer, ForeignKey("usuarios.usuario_id"), nullable=True)

    detalles = relationship("DetalleVenta", back_populates="venta", cascade="all, delete-orphan")
    persona = relationship("Persona", back_populates="ventas")
    metodo_pago = relationship("MetodoPago", back_populates="ventas")
    creador = relationship("Usuario", foreign_keys=[creado_por])
    modificador = relationship("Usuario", foreign_keys=[modificado_por])

    # Relación uno a uno con FacturaElectronica
    factura_electronica = relationship("FacturaElectronica", back_populates="venta", uselist=False, cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Venta(venta_id={self.venta_id}, persona_id={self.persona_id}, total={self.total}, estado='{self.estado}')>"

 