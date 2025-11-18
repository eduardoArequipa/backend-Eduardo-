# backEnd/app/routes/auth.py

from datetime import timedelta, datetime, timezone
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session, joinedload

from .. import auth as auth_utils
from ..database import get_db
from ..schemas.token import Token
from ..schemas.usuario import UsuarioReadAudit
from ..schemas.menu import MenuInDB
from ..models.persona import Persona as DBPersona
from ..models.usuario import Usuario
from ..models.menu import Menu
from ..models.rol import Rol
from ..models.rol_menu import RolMenu
from ..models.enums import EstadoEnum
from ..services.audit_service import AuditService

router = APIRouter(
    prefix="/auth",
    tags=["Auth"]
)

MAX_FAILED_ATTEMPTS = 3
LOCKOUT_TIME_MINUTES = 2

class ForgotPasswordRequest(BaseModel):
    username_or_email: str

class ResetPasswordRequest(BaseModel):
    username_or_email: str
    recovery_code: str
    new_password: str = Field(..., min_length=6, description="La nueva contraseña debe tener al menos 6 caracteres.")

@router.post("/login", response_model=Token)
def login_for_access_token(
    request: Request,
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db)
):
    """
    Autentica un usuario y devuelve un token de acceso JWT.
    Implementa el bloqueo de cuenta por intentos fallidos.
    """
    user = db.query(Usuario).options(
        joinedload(Usuario.persona).joinedload(DBPersona.roles).joinedload(Rol.menus)
    ).filter(Usuario.nombre_usuario == form_data.username).first()

    if not user:
        AuditService.log_action(
            db=db,
            tabla="usuarios",
            accion="LOGIN_FAILED",
            valores_despues={"usuario_intentado": form_data.username, "resultado": "usuario_inexistente"},
            request=request,
            descripcion=f"Intento de login con usuario inexistente: {form_data.username}"
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credenciales inválidas",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # --- Verificación de Estado del Usuario (usando datetimes naive UTC) ---
    current_utc_naive = datetime.utcnow()

    if user.estado == EstadoEnum.bloqueado:
        if user.bloqueado_hasta and user.bloqueado_hasta > current_utc_naive:
            remaining_time = user.bloqueado_hasta - current_utc_naive
            minutes = int(remaining_time.total_seconds() // 60)
            seconds = int(remaining_time.total_seconds() % 60)
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Usuario bloqueado. Inténtelo de nuevo en {minutes} minuto(s) y {seconds} segundo(s).",
            )
        else:
            # El tiempo de bloqueo ha expirado, se marca como activo para el intento actual
            user.estado = EstadoEnum.activo
            user.intentos_fallidos = 0
            user.bloqueado_hasta = None

    if user.estado == EstadoEnum.inactivo:
         raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="La cuenta de usuario se encuentra inactiva. Comuníquese con un administrador.",
        )

    # --- Verificación de Contraseña ---
    if not auth_utils.verify_password(form_data.password, user.contraseña):
        # Contraseña Incorrecta
        user.intentos_fallidos = (user.intentos_fallidos or 0) + 1
        is_being_locked = user.intentos_fallidos >= MAX_FAILED_ATTEMPTS
        
        if is_being_locked:
            user.estado = EstadoEnum.bloqueado
            user.bloqueado_hasta = datetime.utcnow() + timedelta(minutes=LOCKOUT_TIME_MINUTES)

        try:
            db.add(user)
            db.commit()
            db.refresh(user)
        except Exception as e:
            db.rollback()
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error interno del servidor al actualizar intentos de login.")

        AuditService.log_action(
            db=db,
            tabla="usuarios",
            accion="LOGIN_FAILED",
            usuario_id=user.usuario_id,
            registro_id=user.usuario_id,
            valores_despues={"usuario": user.nombre_usuario, "resultado": "contraseña_incorrecta", "intentos_fallidos": user.intentos_fallidos},
            request=request,
            descripcion=f"Login fallido: contraseña incorrecta para {user.nombre_usuario}"
        )

        if is_being_locked:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Usuario bloqueado. Inténtelo de nuevo en {LOCKOUT_TIME_MINUTES} minuto(s) y 0 segundo(s)."
            )
        else:
            remaining_attempts = MAX_FAILED_ATTEMPTS - user.intentos_fallidos
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"Contraseña incorrecta. Le quedan {remaining_attempts} intento(s).",
                headers={"WWW-Authenticate": "Bearer"},
            )
    else:
        # --- Login Exitoso ---
        user.intentos_fallidos = 0
        user.bloqueado_hasta = None
        user.estado = EstadoEnum.activo

        try:
            db.add(user)
            db.commit()
            db.refresh(user)
        except Exception as e:
            db.rollback()
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error interno del servidor al procesar el login exitoso.")

        user_roles = [rol.nombre_rol for rol in user.persona.roles] if user.persona and user.persona.roles else []
        access_token_expires = timedelta(minutes=auth_utils.ACCESS_TOKEN_EXPIRE_MINUTES)
        access_token = auth_utils.create_access_token(
            data={"sub": user.nombre_usuario, "roles": user_roles},
            expires_delta=access_token_expires
        )
        
        AuditService.log_login(db=db, usuario_id=user.usuario_id, request=request, success=True)
        return {"access_token": access_token, "token_type": "bearer"}

@router.get("/me/menus", response_model=List[MenuInDB])
def read_user_menus(current_user: Usuario = Depends(auth_utils.get_current_active_user)):
    if not current_user.persona or not current_user.persona.roles:
        return []
    user_menus = {menu for rol in current_user.persona.roles for menu in rol.menus}
    return sorted(list(user_menus), key=lambda menu: menu.menu_id)

@router.get("/me/menus-with-roles")
def read_user_menus_with_roles(db: Session = Depends(get_db), current_user: Usuario = Depends(auth_utils.get_current_active_user)):
    if not current_user.persona or not current_user.persona.roles:
        return []
    user_role_ids = [rol.rol_id for rol in current_user.persona.roles]
    menus_query = db.query(Menu).options(
        joinedload(Menu.rol_menus).joinedload(RolMenu.rol)
    ).join(RolMenu, Menu.menu_id == RolMenu.menu_id).filter(
        RolMenu.rol_id.in_(user_role_ids)
    ).distinct()
    menus = menus_query.all()
    result = [
        {
            "menu_id": menu.menu_id, "nombre": menu.nombre, "ruta": menu.ruta,
            "descripcion": menu.descripcion, "icono": menu.icono,
            "rol_menu": [{"rol": {"rol_id": rm.rol.rol_id, "nombre_rol": rm.rol.nombre_rol}} for rm in menu.rol_menus]
        } for menu in menus
    ]
    result.sort(key=lambda m: m["menu_id"])
    return result

@router.post("/forgot-password-request", status_code=status.HTTP_200_OK)
async def forgot_password_request(request: ForgotPasswordRequest, db: Session = Depends(get_db)):
    user = db.query(Usuario).options(joinedload(Usuario.persona)).filter(Usuario.nombre_usuario == request.username_or_email).first()
    if not user:
        persona = db.query(DBPersona).options(joinedload(DBPersona.usuario)).filter(DBPersona.email == request.username_or_email).first()
        if persona and persona.usuario:
            user = persona.usuario
    if not user or not (user.persona and user.persona.email) or user.estado == EstadoEnum.inactivo:
        # Por seguridad, no revelamos si el usuario no existe, no tiene email, o está inactivo.
        return {"message": f"Si la dirección de correo o el usuario son válidos , se ha enviado un código de recuperación."}
    
    recovery_code = auth_utils.generate_recovery_code()
    expiration_time = datetime.utcnow() + timedelta(minutes=auth_utils.RECOVERY_CODE_EXPIRE_MINUTES)
    user.codigo_recuperacion = recovery_code
    user.expiracion_codigo_recuperacion = expiration_time
    try:
        db.add(user)
        db.commit()
        db.refresh(user)
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error interno del servidor al procesar la solicitud de recuperación.")
    
    auth_utils.send_recovery_email(user.persona.email, user.nombre_usuario, recovery_code)
    return {"message": "Si la dirección de correo o el usuario son válidos, se ha enviado un código de recuperación."}

@router.post("/reset-password", status_code=status.HTTP_200_OK)
def reset_password(request: ResetPasswordRequest, db: Session = Depends(get_db)):
    user = db.query(Usuario).options(joinedload(Usuario.persona)).filter(Usuario.nombre_usuario == request.username_or_email).first()
    if not user:
        persona = db.query(DBPersona).options(joinedload(DBPersona.usuario)).filter(DBPersona.email == request.username_or_email).first()
        if persona and persona.usuario:
            user = persona.usuario
    if not user:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Usuario o correo electrónico no encontrado.")

    # No permitir el reseteo de contraseña para usuarios inactivos
    if user.estado == EstadoEnum.inactivo:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Esta cuenta está inactiva y no puede restablecer la contraseña. Comuníquese con un administrador."
        )

    current_utc_naive = datetime.utcnow()
    
    # Asegurarse de que la comparación de fechas sea siempre naive vs naive
    expiracion_naive = user.expiracion_codigo_recuperacion
    if expiracion_naive and expiracion_naive.tzinfo is not None:
        expiracion_naive = expiracion_naive.replace(tzinfo=None)

    if not user.codigo_recuperacion or user.codigo_recuperacion != request.recovery_code or expiracion_naive is None or current_utc_naive > expiracion_naive:
        if user.codigo_recuperacion:
            user.codigo_recuperacion = None
            user.expiracion_codigo_recuperacion = None
            try:
                db.add(user)
                db.commit()
            except Exception:
                db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Código de recuperación expirado o inválido. Por favor, solicita uno nuevo.")

    user.contraseña = auth_utils.get_password_hash(request.new_password)
    user.codigo_recuperacion = None
    user.expiracion_codigo_recuperacion = None
    user.intentos_fallidos = 0
    user.bloqueado_hasta = None
    user.estado = EstadoEnum.activo
    try:
        db.add(user)
        db.commit()
        db.refresh(user)
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error interno del servidor al restablecer la contraseña.")
    return {"message": "Contraseña restablecida exitosamente. Ahora puede iniciar sesión."}

@router.get("/me", response_model=UsuarioReadAudit)
def read_users_me(current_user: Usuario = Depends(auth_utils.get_current_active_user)):
    return current_user