# backEnd/app/routes/audit_logs.py

from typing import Optional, List
from datetime import datetime, date
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import or_, func, desc

from ..database import get_db
from .. import auth as auth_utils
from ..models.audit_log import AuditLog
from ..models.usuario import Usuario
from ..schemas.audit_log import (
    AuditLogRead,
    AuditLogPagination,
    AuditLogFilter,
    AuditLogStats
)

router = APIRouter(
    prefix="/audit-logs",
    tags=["Audit Logs"]
)


@router.get("/", response_model=AuditLogPagination)
def get_audit_logs(
    # Filtros de búsqueda
    usuario_id: Optional[int] = Query(None, description="Filtrar por ID de usuario"),
    tabla: Optional[str] = Query(None, description="Filtrar por tabla afectada"),
    accion: Optional[str] = Query(None, description="Filtrar por tipo de acción"),
    fecha_desde: Optional[date] = Query(None, description="Fecha desde (YYYY-MM-DD)"),
    fecha_hasta: Optional[date] = Query(None, description="Fecha hasta (YYYY-MM-DD)"),
    ip_address: Optional[str] = Query(None, description="Filtrar por dirección IP"),
    search: Optional[str] = Query(None, description="Búsqueda general en descripción"),

    # Paginación
    skip: int = Query(0, ge=0, description="Número de registros a omitir"),
    limit: int = Query(50, gt=0, le=500, description="Número máximo de registros a devolver"),

    # Dependencias
    db: Session = Depends(get_db),
    current_user: auth_utils.Usuario = Depends(auth_utils.require_menu_access("/audit-logs"))
):
    """
    Obtiene logs de auditoría con filtros y paginación.
    Solo accesible para usuarios con permisos de auditoría.
    """

    # Construir la consulta base con joins necesarios
    query = db.query(AuditLog).options(
        joinedload(AuditLog.usuario)
    ).order_by(desc(AuditLog.fecha))

    # Aplicar filtros
    if usuario_id:
        query = query.filter(AuditLog.usuario_id == usuario_id)

    if tabla:
        query = query.filter(AuditLog.tabla.ilike(f"%{tabla}%"))

    if accion:
        query = query.filter(AuditLog.accion == accion)

    if fecha_desde:
        query = query.filter(AuditLog.fecha >= fecha_desde)

    if fecha_hasta:
        # Incluir todo el día hasta las 23:59:59
        fecha_hasta_end = datetime.combine(fecha_hasta, datetime.max.time())
        query = query.filter(AuditLog.fecha <= fecha_hasta_end)

    if ip_address:
        query = query.filter(AuditLog.ip_address == ip_address)

    if search:
        query = query.filter(
            or_(
                AuditLog.descripcion.ilike(f"%{search}%"),
                AuditLog.tabla.ilike(f"%{search}%")
            )
        )

    # Contar total antes de aplicar paginación
    total = query.count()

    # Aplicar paginación
    logs = query.offset(skip).limit(limit).all()

    # Enriquecer los datos con información del usuario
    for log in logs:
        if log.usuario:
            log.usuario_nombre = log.usuario.nombre_usuario
        else:
            log.usuario_nombre = "Sistema"

    return {
        "items": logs,
        "total": total,
        "skip": skip,
        "limit": limit
    }


@router.get("/stats", response_model=AuditLogStats)
def get_audit_stats(
    fecha_desde: Optional[date] = Query(None, description="Fecha desde para estadísticas"),
    fecha_hasta: Optional[date] = Query(None, description="Fecha hasta para estadísticas"),
    db: Session = Depends(get_db),
    current_user: auth_utils.Usuario = Depends(auth_utils.require_menu_access("/audit-logs"))
):
    """
    Obtiene estadísticas de auditoría.
    """

    # Consulta base
    query = db.query(AuditLog)

    # Aplicar filtros de fecha si se proporcionan
    if fecha_desde:
        query = query.filter(AuditLog.fecha >= fecha_desde)

    if fecha_hasta:
        fecha_hasta_end = datetime.combine(fecha_hasta, datetime.max.time())
        query = query.filter(AuditLog.fecha <= fecha_hasta_end)

    # Total de logs
    total_logs = query.count()

    # Logs de hoy
    today = date.today()
    logs_hoy = db.query(AuditLog).filter(
        func.date(AuditLog.fecha) == today
    ).count()

    # Acciones por tipo
    acciones_por_tipo = {}
    acciones_query = query.with_entities(
        AuditLog.accion,
        func.count(AuditLog.log_id).label('count')
    ).group_by(AuditLog.accion).all()

    for accion, count in acciones_query:
        acciones_por_tipo[accion] = count

    # Usuarios más activos (top 5)
    usuarios_activos = query.join(Usuario).with_entities(
        Usuario.nombre_usuario,
        func.count(AuditLog.log_id).label('count')
    ).group_by(Usuario.usuario_id, Usuario.nombre_usuario)\
     .order_by(desc('count'))\
     .limit(5).all()

    usuarios_mas_activos = [
        {"usuario": usuario, "acciones": count}
        for usuario, count in usuarios_activos
    ]

    # IPs más frecuentes (top 5)
    ips_frecuentes = query.filter(AuditLog.ip_address.isnot(None))\
        .with_entities(
            AuditLog.ip_address,
            func.count(AuditLog.log_id).label('count')
        ).group_by(AuditLog.ip_address)\
         .order_by(desc('count'))\
         .limit(5).all()

    ips_mas_frecuentes = [
        {"ip": ip, "acciones": count}
        for ip, count in ips_frecuentes
    ]

    return {
        "total_logs": total_logs,
        "logs_hoy": logs_hoy,
        "acciones_por_tipo": acciones_por_tipo,
        "usuarios_mas_activos": usuarios_mas_activos,
        "ips_mas_frecuentes": ips_mas_frecuentes
    }


@router.get("/actions", response_model=List[str])
def get_available_actions(
    db: Session = Depends(get_db),
    current_user: auth_utils.Usuario = Depends(auth_utils.require_menu_access("/audit-logs"))
):
    """
    Obtiene la lista de acciones disponibles para filtros.
    """

    actions = db.query(AuditLog.accion).distinct().all()
    return [action[0] for action in actions if action[0]]


@router.get("/tables", response_model=List[str])
def get_available_tables(
    db: Session = Depends(get_db),
    current_user: auth_utils.Usuario = Depends(auth_utils.require_menu_access("/audit-logs"))
):
    """
    Obtiene la lista de tablas disponibles para filtros.
    """

    tables = db.query(AuditLog.tabla).distinct().all()
    return [table[0] for table in tables if table[0]]


@router.get("/{log_id}", response_model=AuditLogRead)
def get_audit_log_detail(
    log_id: int,
    db: Session = Depends(get_db),
    current_user: auth_utils.Usuario = Depends(auth_utils.require_menu_access("/audit-logs"))
):
    """
    Obtiene los detalles de un log específico.
    """

    log = db.query(AuditLog).options(
        joinedload(AuditLog.usuario)
    ).filter(AuditLog.log_id == log_id).first()

    if not log:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Log de auditoría no encontrado"
        )

    # Enriquecer con nombre de usuario
    if log.usuario:
        log.usuario_nombre = log.usuario.nombre_usuario
    else:
        log.usuario_nombre = "Sistema"

    return log