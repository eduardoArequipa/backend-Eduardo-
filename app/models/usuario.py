# Componente1_SistemaWeb/backEnd/app/models/usuario.py

from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Enum, func
from sqlalchemy.orm import relationship
from sqlalchemy.sql.schema import UniqueConstraint
from .base import Base
from .enums import EstadoEnum # Asumiendo que EstadoEnum está correctamente definido
from datetime import datetime
# Importamos el modelo de asociación para usuario_roles
# Si ya eliminaste usuario_roles y usas PersonaRol, asegúrate de que no haya referencias aquí.


class Usuario(Base):
    __tablename__ = 'usuarios'

    usuario_id = Column(Integer, primary_key=True, index=True)
    # La relación 1:1 con persona. 'UNIQUE=True' en el FK refuerza la unicidad en este lado.
    persona_id = Column(Integer, ForeignKey('personas.persona_id', ondelete='RESTRICT'), unique=True, nullable=False)
    nombre_usuario = Column(String(50), unique=True, nullable=False, index=True)
    contraseña = Column(String(255), nullable=False) # Almacenar el hash aquí
    intentos_fallidos = Column(Integer, default=0)
    bloqueado_hasta = Column(DateTime, nullable=True)
    estado = Column(Enum(EstadoEnum), default=EstadoEnum.activo) # Usamos el Enum
    creado_por = Column(Integer, ForeignKey('usuarios.usuario_id', ondelete='SET NULL'), nullable=True)
    modificado_por = Column(Integer, ForeignKey('usuarios.usuario_id', ondelete='SET NULL'), nullable=True)
    foto_ruta = Column(String(255), nullable=True) # Ruta a la foto

    codigo_recuperacion = Column(String(100), nullable=True) # Almacena el código de recuperación
    expiracion_codigo_recuperacion = Column(DateTime(timezone=True), nullable=True)

    # Campos de auditoría en español
    fecha_creacion = Column(DateTime, default=func.now(), nullable=True)
    fecha_modificacion = Column(DateTime, default=func.now(), onupdate=func.now(), nullable=True)

    # Relación 1:1 con Persona
    persona = relationship("Persona", back_populates="usuario", uselist=False) # uselist=False para 1:1

    # Auto-referencia para creador y modificador
    # Es importante especificar remote_side para auto-referencias
    creador = relationship("Usuario", remote_side=[usuario_id], foreign_keys=[creado_por], backref="usuarios_creados")
    modificador = relationship("Usuario", remote_side=[usuario_id], foreign_keys=[modificado_por], backref="usuarios_modificados")

    # Relación 1:N con Compra (compras que este usuario creó - campo de auditoría)
    # La foreign_key está en el modelo Compra (Compra.creado_por)
    compras_creadas = relationship("Compra", foreign_keys="[Compra.creado_por]", back_populates="creador") # <-- ¡CORREGIDO AQUÍ!

    # Relación 1:N con Compra (compras que este usuario modificó - campo de auditoría)
    # La foreign_key está en el modelo Compra (Compra.modificado_por)
    compras_modificadas = relationship("Compra", foreign_keys="[Compra.modificado_por]", back_populates="modificador") # <-- ¡CORREGIDO AQUÍ!

    def __repr__(self):
        return f"<Usuario(id={self.usuario_id}, nombre_usuario='{self.nombre_usuario}', persona_id={self.persona_id})>"