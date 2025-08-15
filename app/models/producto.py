from sqlalchemy import Column, Integer, String, DECIMAL, Float, ForeignKey, Enum, DateTime, CheckConstraint, Numeric
from sqlalchemy.orm import relationship

from .base import Base
from .enums import EstadoEnum

from .categoria import Categoria
from .usuario import Usuario
from .unidad_medida import UnidadMedida
from .marca import Marca

class Producto(Base):
    __tablename__ = "productos"
    
    producto_id = Column(Integer, primary_key=True, index=True) # Clave primaria
    imagen_ruta = Column(String(255), nullable=True) # Puede ser nulo
    codigo = Column(String(50), unique=True, nullable=False) # Código único y no nulo
    nombre = Column(String(100), nullable=False) # Nombre no nulo
    precio_compra = Column(DECIMAL(10, 2), nullable=False, default= 10) # Precio decimal no nulo
    precio_venta = Column(DECIMAL(10, 2), nullable=False, default= 10.0) # Precio decimal no nulo

    stock = Column(Numeric(10, 2), default=0, nullable=False) # Stock ahora es NUMERIC
    stock_minimo = Column(Integer, nullable=False) # Stock mínimo no nulo
    
    # Renombrado a unidad_inventario_id
    unidad_inventario_id = Column(Integer, ForeignKey('unidades_medida.unidad_id'), nullable=False)
    marca_id = Column(Integer, ForeignKey('marcas.marca_id'), nullable=False) # FK no nula
    
    # Nuevo campo para la unidad de compra predeterminada
    unidad_compra_predeterminada = Column(String(50), nullable=True)

    # Constraint de check para stock no negativo
    __table_args__ = (
        CheckConstraint('stock >= 0', name='chk_stock_no_negativo'),
    )
    
    # Clave Foránea a la tabla categorias
    categoria_id = Column(Integer, ForeignKey('categorias.categoria_id'), nullable=False) # FK no nula

    # Campo de estado con Enum y default
    estado = Column(Enum(EstadoEnum), default=EstadoEnum.activo, nullable=False) # Usa el Enum y default
    creado_por = Column(Integer, ForeignKey('usuarios.usuario_id', ondelete='SET NULL'), nullable=True) # FK, puede ser nulo
    modificado_por = Column(Integer, ForeignKey('usuarios.usuario_id', ondelete='SET NULL'), nullable=True) # FK, puede ser nulo

    categoria = relationship("Categoria", back_populates="productos") # Asume que Categoria tiene back_populates="productos"
    creador = relationship("Usuario", foreign_keys=[creado_por])
    modificador = relationship("Usuario", foreign_keys=[modificado_por])
    detalle_compras = relationship("DetalleCompra", back_populates="producto")
    
    # Relación renombrada
    unidad_inventario = relationship("UnidadMedida", back_populates="productos")
    marca = relationship("Marca", back_populates="productos")

    # Nueva relación con las conversiones
    conversiones = relationship("ConversionesCompra", back_populates="producto", cascade="all, delete-orphan")

    # El método __repr__ es útil para la depuración
    def __repr__(self):
        return f"<Producto(producto_id={self.producto_id}, codigo='{self.codigo}', nombre='{self.nombre}', categoria_id={self.categoria_id}, estado='{self.estado}')>"
