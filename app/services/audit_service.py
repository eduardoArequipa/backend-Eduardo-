# backEnd/app/services/audit_service.py

from typing import Optional, Dict, Any
from datetime import datetime
from sqlalchemy.orm import Session
from fastapi import Request
from ..models.audit_log import AuditLog
from ..models.usuario import Usuario
from .geolocation_service import GeolocationService


class AuditService:
    """Servicio para manejar logs de auditoría"""

    @staticmethod
    def log_action(
        db: Session,
        tabla: str,
        accion: str,
        usuario_id: Optional[int] = None,
        registro_id: Optional[int] = None,
        valores_antes: Optional[Dict[str, Any]] = None,
        valores_despues: Optional[Dict[str, Any]] = None,
        request: Optional[Request] = None,
        descripcion: Optional[str] = None
    ) -> AuditLog:
        """
        Registra una acción en el log de auditoría

        Args:
            db: Sesión de base de datos
            tabla: Nombre de la tabla afectada
            accion: Tipo de acción (CREATE, UPDATE, DELETE, LOGIN, etc.)
            usuario_id: ID del usuario que realizó la acción
            registro_id: ID del registro afectado
            valores_antes: Estado anterior del registro (para UPDATE/DELETE)
            valores_despues: Estado nuevo del registro (para CREATE/UPDATE)
            request: Objeto Request de FastAPI para obtener IP y user-agent
            descripcion: Descripción legible de la acción
        """

        # Obtener información del request si está disponible
        ip_address = None
        user_agent = None
        pais = None
        ciudad = None
        region = None

        if request:
            # Obtener IP real considerando proxies
            ip_address = request.headers.get("X-Forwarded-For", "").split(",")[0].strip()
            if not ip_address:
                ip_address = request.headers.get("X-Real-IP", "")
            if not ip_address:
                ip_address = str(request.client.host) if request.client else None

            user_agent = request.headers.get("User-Agent", "")

            # Obtener geolocalización si tenemos IP
            if ip_address:
                try:
                    location_data = GeolocationService.get_location_from_ip(ip_address)
                    pais = location_data.get("pais")
                    ciudad = location_data.get("ciudad")
                    region = location_data.get("region")
                except Exception as e:
                    # Log el error pero continúa sin geolocalización
                    print(f"Error en geolocalización: {e}")

        # Crear el log
        audit_log = AuditLog(
            usuario_id=usuario_id,
            tabla=tabla,
            accion=accion,
            registro_id=registro_id,
            valores_antes=valores_antes,
            valores_despues=valores_despues,
            ip_address=ip_address,
            user_agent=user_agent,
            descripcion=descripcion,
            pais=pais,
            ciudad=ciudad,
            region=region
        )

        db.add(audit_log)
        db.commit()
        db.refresh(audit_log)

        return audit_log

    @staticmethod
    def log_login(
        db: Session,
        usuario_id: int,
        request: Optional[Request] = None,
        success: bool = True
    ) -> AuditLog:
        """Registra un intento de login"""
        descripcion = f"Login {'exitoso' if success else 'fallido'}"

        # Para login exitoso, incluir información básica del usuario
        valores_despues = None
        if success:
            valores_despues = {
                "accion": "login_exitoso",
                "timestamp": datetime.now().isoformat(),
                "usuario_id": usuario_id
            }

        return AuditService.log_action(
            db=db,
            tabla="usuarios",
            accion="LOGIN" if success else "LOGIN_FAILED",
            usuario_id=usuario_id if success else None,
            registro_id=usuario_id,  # Agregar el usuario_id como registro_id
            valores_despues=valores_despues,
            request=request,
            descripcion=descripcion
        )

    @staticmethod
    def log_logout(
        db: Session,
        usuario_id: int,
        request: Optional[Request] = None
    ) -> AuditLog:
        """Registra un logout"""
        return AuditService.log_action(
            db=db,
            tabla="usuarios",
            accion="LOGOUT",
            usuario_id=usuario_id,
            request=request,
            descripcion="Logout del usuario"
        )

    @staticmethod
    def log_create(
        db: Session,
        tabla: str,
        registro_id: int,
        valores_despues: Dict[str, Any],
        usuario_id: Optional[int] = None,
        request: Optional[Request] = None
    ) -> AuditLog:
        """Registra la creación de un registro"""
        descripcion = f"Nuevo {tabla[:-1]} creado"  # usuarios -> usuario

        return AuditService.log_action(
            db=db,
            tabla=tabla,
            accion="CREATE",
            usuario_id=usuario_id,
            registro_id=registro_id,
            valores_despues=valores_despues,
            request=request,
            descripcion=descripcion
        )

    @staticmethod
    def log_update(
        db: Session,
        tabla: str,
        registro_id: int,
        valores_antes: Dict[str, Any],
        valores_despues: Dict[str, Any],
        usuario_id: Optional[int] = None,
        request: Optional[Request] = None
    ) -> AuditLog:
        """Registra la actualización de un registro"""
        descripcion = f"{tabla[:-1].capitalize()} actualizado"  # usuarios -> Usuario

        return AuditService.log_action(
            db=db,
            tabla=tabla,
            accion="UPDATE",
            usuario_id=usuario_id,
            registro_id=registro_id,
            valores_antes=valores_antes,
            valores_despues=valores_despues,
            request=request,
            descripcion=descripcion
        )

    @staticmethod
    def log_delete(
        db: Session,
        tabla: str,
        registro_id: int,
        valores_antes: Dict[str, Any],
        usuario_id: Optional[int] = None,
        request: Optional[Request] = None
    ) -> AuditLog:
        """Registra la eliminación de un registro"""
        descripcion = f"{tabla[:-1].capitalize()} eliminado"  # usuarios -> Usuario

        return AuditService.log_action(
            db=db,
            tabla=tabla,
            accion="DELETE",
            usuario_id=usuario_id,
            registro_id=registro_id,
            valores_antes=valores_antes,
            request=request,
            descripcion=descripcion
        )

    @staticmethod
    def serialize_model(model_instance) -> Dict[str, Any]:
        """
        Convierte una instancia del modelo SQLAlchemy a un diccionario
        para almacenar en los logs
        """
        if not model_instance:
            return {}

        result = {}
        for column in model_instance.__table__.columns:
            value = getattr(model_instance, column.name)
            # Convertir tipos especiales a strings para JSON
            if hasattr(value, 'isoformat'):  # datetime
                result[column.name] = value.isoformat()
            elif hasattr(value, '__str__') and not isinstance(value, (str, int, float, bool)):
                result[column.name] = str(value)
            else:
                result[column.name] = value

        return result