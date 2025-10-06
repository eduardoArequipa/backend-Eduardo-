# backEnd/app/models/compra.py
from sqlalchemy import Column, Integer, ForeignKey, DateTime, DECIMAL, Enum, String
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func 

from .base import Base 
from .enums import EstadoCompraEnum 



class Compra(Base):
    __tablename__ = "compras" 
    compra_id = Column(Integer, primary_key=True, index=True) 
    proveedor_id = Column(Integer, ForeignKey('proveedores.proveedor_id'), nullable=False)
    fecha_compra = Column(DateTime, server_default=func.now(), nullable=False)
    total = Column(DECIMAL(10, 2), nullable=False) 
    estado = Column(Enum(EstadoCompraEnum), default=EstadoCompraEnum.pendiente, nullable=False) 
    creado_por = Column(Integer, ForeignKey('usuarios.usuario_id', ondelete='SET NULL'), nullable=True)
    modificado_por = Column(Integer, ForeignKey('usuarios.usuario_id', ondelete='SET NULL'), nullable=True)
    
    proveedor = relationship("Proveedor", back_populates="compras")
    creador = relationship("Usuario", foreign_keys=[creado_por], back_populates="compras_creadas")
    modificador = relationship("Usuario", foreign_keys=[modificado_por], back_populates="compras_modificadas")
    detalles = relationship("DetalleCompra", back_populates="compra", cascade="all, delete-orphan")


    # El método __repr__ es útil para la depuración
    def __repr__(self):
        return f"<Compra(compra_id={self.compra_id}, proveedor_id={self.proveedor_id}, total={self.total}, estado='{self.estado}')>"


 