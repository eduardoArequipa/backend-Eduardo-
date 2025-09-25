# backEnd/app/schemas/audit_log.py

from typing import Optional, Dict, Any
from datetime import datetime
from pydantic import BaseModel
from .pagination import Pagination


class AuditLogBase(BaseModel):
    tabla: str
    accion: str  # 'CREATE', 'UPDATE', 'DELETE', 'LOGIN'
    registro_id: Optional[int] = None
    valores_antes: Optional[Dict[str, Any]] = None
    valores_despues: Optional[Dict[str, Any]] = None
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    descripcion: Optional[str] = None
    pais: Optional[str] = None
    ciudad: Optional[str] = None
    region: Optional[str] = None


class AuditLogCreate(AuditLogBase):
    usuario_id: Optional[int] = None


class AuditLogRead(AuditLogBase):
    log_id: int
    usuario_id: Optional[int] = None
    fecha: datetime

    # Información del usuario (relación)
    usuario_nombre: Optional[str] = None

    class Config:
        from_attributes = True


class AuditLogFilter(BaseModel):
    """Filtros para búsqueda de logs"""
    usuario_id: Optional[int] = None
    tabla: Optional[str] = None
    accion: Optional[str] = None
    fecha_desde: Optional[datetime] = None
    fecha_hasta: Optional[datetime] = None
    ip_address: Optional[str] = None
    search: Optional[str] = None  # Búsqueda general


class AuditLogStats(BaseModel):
    """Estadísticas de auditoría"""
    total_logs: int
    logs_hoy: int
    acciones_por_tipo: Dict[str, int]
    usuarios_mas_activos: list
    ips_mas_frecuentes: list


# Paginación para logs
AuditLogPagination = Pagination[AuditLogRead]