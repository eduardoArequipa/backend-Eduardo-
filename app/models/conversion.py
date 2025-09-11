from sqlalchemy import Column, Integer, String, Boolean, ForeignKey, DECIMAL
from sqlalchemy.orm import relationship
from .base import Base

class Conversion(Base):
    __tablename__ = "conversiones"

    id = Column(Integer, primary_key=True, index=True)
    nombre_presentacion = Column(String(100), nullable=False)
    producto_id = Column(Integer, ForeignKey("productos.producto_id", ondelete="CASCADE"), nullable=False)
    unidades_por_presentacion = Column(DECIMAL(10, 2), nullable=False)
    
    es_para_compra = Column(Boolean, default=False, nullable=False)
    es_para_venta = Column(Boolean, default=False, nullable=False)
    es_activo = Column(Boolean, default=True)
    descripcion_detallada = Column(String(100), nullable=True)

    # Relación inversa con Producto
    producto = relationship("Producto", back_populates="conversiones")
