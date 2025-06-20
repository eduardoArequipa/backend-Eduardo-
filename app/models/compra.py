# backEnd/app/models/compra.py
from sqlalchemy import Column, Integer, ForeignKey, DateTime, DECIMAL, Enum, String
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func # Importa func para usar funciones SQL como CURRENT_TIMESTAMP

from .base import Base # Importa la base declarativa
from .enums import EstadoCompraEnum  # Necesitaremos un nuevo Enum para el estado de compra
# Importa los modelos relacionados para definir las relaciones
from .usuario import Usuario # Asumiendo que tu modelo de usuario se llama Usuario


# Nota: Este modelo mapea la tabla compras.

class Compra(Base):
    __tablename__ = "compras" # Mapea a la tabla 'compras' en la base de datos

    compra_id = Column(Integer, primary_key=True, index=True) # Clave primaria

    # Claves Foráneas a Proveedor y Usuario (quien realizó la compra en el sistema)
    proveedor_id = Column(Integer, ForeignKey('proveedores.proveedor_id'), nullable=False)

    fecha_compra = Column(DateTime, server_default=func.now(), nullable=False) # Fecha con default a la hora actual del servidor
    total = Column(DECIMAL(10, 2), nullable=False) # Total de la compra

    # Campo de estado con Enum y default
    estado = Column(Enum(EstadoCompraEnum), default=EstadoCompraEnum.pendiente, nullable=False) # Usa el nuevo Enum y default

    # Campos de auditoría (quién creó/modificó)
    creado_por = Column(Integer, ForeignKey('usuarios.usuario_id', ondelete='SET NULL'), nullable=True)
    modificado_por = Column(Integer, ForeignKey('usuarios.usuario_id', ondelete='SET NULL'), nullable=True)

    # Definir relaciones ORM
    # Relación N:1 con Proveedor
    proveedor = relationship("Proveedor", back_populates="compras")

    # Relación N:1 con Usuario (quien realizó la compra)

    # Relación N:1 con Usuario (creador)
    creador = relationship("Usuario", foreign_keys=[creado_por], back_populates="compras_creadas")

    # Relación N:1 con Usuario (modificador)
    modificador = relationship("Usuario", foreign_keys=[modificado_por], back_populates="compras_modificadas")

    # Relación 1:N con DetalleCompra (una compra tiene muchos detalles)
    detalles = relationship("DetalleCompra", back_populates="compra", cascade="all, delete-orphan") # Cascade para eliminar detalles si se elimina la compra


    # El método __repr__ es útil para la depuración
    def __repr__(self):
        return f"<Compra(compra_id={self.compra_id}, proveedor_id={self.proveedor_id}, total={self.total}, estado='{self.estado}')>"


 