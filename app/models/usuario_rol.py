# backEnd/app/models/usuario_rol.py
from sqlalchemy import Column, Integer, ForeignKey, DateTime, PrimaryKeyConstraint
from .base import Base
from datetime import datetime

class UsuarioRol(Base):
    # Usamos el nombre EXACTO de la tabla proporcionada en tu SQL
    __tablename__ = 'usuario_roles'

    usuario_id = Column(Integer, ForeignKey('usuarios.usuario_id', ondelete='CASCADE'), nullable=False)
    rol_id = Column(Integer, ForeignKey('roles.rol_id', ondelete='CASCADE'), nullable=False)

    # Definimos la clave primaria compuesta
    __table_args__ = (
        PrimaryKeyConstraint('usuario_id', 'rol_id'),
    )

    # Nota: Con SQLAlchemy 2.0+, no necesitas definir relationships aquí
    # si solo es una tabla de asociación simple utilizada en secondary=
    # en los modelos Usuario y Rol.

    def __repr__(self):
        return f"<UsuarioRol(usuario_id={self.usuario_id}, rol_id={self.rol_id})>"