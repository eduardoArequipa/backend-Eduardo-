# backEnd/app/models/audit_log.py

from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text, func
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import JSONB, INET
from .base import Base
from datetime import datetime


class AuditLog(Base):
    __tablename__ = 'audit_logs'

    log_id = Column(Integer, primary_key=True, index=True)
    usuario_id = Column(Integer, ForeignKey('usuarios.usuario_id', ondelete='SET NULL'), nullable=True)
    tabla = Column(String(50), nullable=False, index=True)  # 'usuarios', 'productos', etc.
    accion = Column(String(50), nullable=False, index=True)  # 'CREATE', 'UPDATE', 'DELETE', 'LOGIN'
    registro_id = Column(Integer, nullable=True)  # ID del registro afectado

    # Datos del cambio
    valores_antes = Column(JSONB, nullable=True)  # Estado anterior (UPDATE/DELETE)
    valores_despues = Column(JSONB, nullable=True)  # Estado nuevo (CREATE/UPDATE)

    # Información de contexto
    ip_address = Column(INET, nullable=True)  # IP del usuario
    user_agent = Column(Text, nullable=True)  # Información del navegador
    descripcion = Column(Text, nullable=True)  # Descripción legible de la acción

    # Geolocalización (para implementar después)
    pais = Column(String(100), nullable=True)
    ciudad = Column(String(100), nullable=True)
    region = Column(String(100), nullable=True)

    # Timestamp
    fecha = Column(DateTime, default=func.now(), nullable=False, index=True)

    # Relación con Usuario
    usuario = relationship("Usuario", foreign_keys=[usuario_id], backref="audit_logs")

    def __repr__(self):
        return f"<AuditLog(id={self.log_id}, usuario={self.usuario_id}, tabla='{self.tabla}', accion='{self.accion}')>"