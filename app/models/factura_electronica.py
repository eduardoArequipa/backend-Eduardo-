# backEnd/app/models/factura_electronica.py
from sqlalchemy import Column, Integer, String, Text, TIMESTAMP, ForeignKey, func
from sqlalchemy.orm import relationship
from .base import Base

class FacturaElectronica(Base):
    __tablename__ = "facturas_electronicas"

    factura_id = Column(Integer, primary_key=True, index=True)
    venta_id = Column(Integer, ForeignKey("ventas.venta_id", ondelete="CASCADE"), nullable=False, unique=True)
    
    cuf = Column(String(255), nullable=True)
    estado = Column(String(50), nullable=True)
    tesabiz_id = Column(String(255), nullable=True)
    
    fecha_emision = Column(TIMESTAMP(timezone=True), server_default=func.now())
    detalles_respuesta = Column(Text, nullable=True)

    # Relación inversa para que desde FacturaElectronica se pueda acceder a la Venta
    venta = relationship("Venta", back_populates="factura_electronica")

    def __repr__(self):
        return f"<FacturaElectronica(id={self.factura_id}, venta_id={self.venta_id}, estado='{self.estado}')>"
