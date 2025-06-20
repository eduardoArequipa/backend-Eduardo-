# backEnd/app/routes/auth.py
from datetime import timedelta, datetime, timezone # Importar timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel, Field, EmailStr
from sqlalchemy.orm import Session, joinedload
import pytz # Importar pytz para manejar zonas horarias, si no lo tienes, instálalo: pip install pytz

# Importar tus utilidades de auth
from .. import auth as auth_utils
from ..database import get_db
from ..schemas.token import Token
from ..schemas.usuario import UsuarioReadAudit
from ..models.persona import Persona as DBPersona # Añadir esta importación si auth_utils.Persona no es suficiente o no existe

router = APIRouter(
    prefix="/auth",
    tags=["Auth"]
)

# --- Constantes para el bloqueo de cuenta ---
MAX_FAILED_ATTEMPTS = 5
LOCKOUT_TIME_MINUTES = 15
# ------------------------------------------

# --- Esquemas Pydantic para los nuevos endpoints ---
class ForgotPasswordRequest(BaseModel):
    username_or_email: str

class ResetPasswordRequest(BaseModel):
    username_or_email: str
    recovery_code: str
    new_password: str = Field(..., min_length=6, description="La nueva contraseña debe tener al menos 6 caracteres.")

# ---------------------------------------------------

# Helper function to make naive datetimes timezone-aware (UTC)
# This assumes any naive datetime in your DB is meant to be UTC.
def make_datetime_utc_aware(dt: Optional[datetime]) -> Optional[datetime]:
    if dt and dt.tzinfo is None:
        # Assume it's UTC if it's naive, then make it aware
        return dt.replace(tzinfo=timezone.utc)
    return dt

# Endpoint de login usando form-data
@router.post("/login", response_model=Token)
def login_for_access_token(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db)
):
    """
    Autentica un usuario y devuelve un token de acceso JWT.
    Implementa el bloqueo de cuenta por intentos fallidos.
    """
    print(f"\n--- Intento de Login para usuario: {form_data.username} ---")

    user = db.query(auth_utils.Usuario).options(
        joinedload(auth_utils.Usuario.persona)
    ).filter(auth_utils.Usuario.nombre_usuario == form_data.username).first()

    if not user:
        print(f"DEBUG: Usuario '{form_data.username}' no encontrado.")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credenciales inválidas",
            headers={"WWW-Authenticate": "Bearer"},
        )

    print(f"DEBUG: Usuario encontrado. ID: {user.usuario_id}, Nombre: {user.nombre_usuario}")
    print(f"DEBUG: Estado inicial: {user.estado}, Intentos fallidos: {user.intentos_fallidos}, Bloqueado hasta: {user.bloqueado_hasta}")

    # Make user.bloqueado_hasta timezone-aware before comparison
    user_bloqueado_hasta_aware = make_datetime_utc_aware(user.bloqueado_hasta)
    current_utc_time = datetime.now(timezone.utc)

    if user_bloqueado_hasta_aware and user_bloqueado_hasta_aware > current_utc_time:
        remaining_time_seconds = (user_bloqueado_hasta_aware - current_utc_time).total_seconds()
        minutes = int(remaining_time_seconds // 60)
        seconds = int(remaining_time_seconds % 60)
        print(f"DEBUG: Usuario '{user.nombre_usuario}' actualmente bloqueado. Tiempo restante: {minutes}m {seconds}s")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Usuario bloqueado. Inténtelo de nuevo en {minutes} minuto(s) y {seconds} segundo(s).",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if user.estado != auth_utils.EstadoEnum.activo:
         print(f"DEBUG: Usuario '{user.nombre_usuario}' inactivo o bloqueado por administración.")
         raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Usuario inactivo o bloqueado",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not auth_utils.verify_password(form_data.password, user.contraseña):
        user.intentos_fallidos = (user.intentos_fallidos or 0) + 1
        print(f"DEBUG: Contraseña incorrecta. Intentos fallidos incrementados a: {user.intentos_fallidos}")
        try:
            db.add(user)
            db.commit()
            db.refresh(user)
            print(f"DEBUG: Intentos fallidos guardados y refrescados. Valor actual: {user.intentos_fallidos}")
        except Exception as e:
            db.rollback()
            print(f"ERROR: Fallo al guardar intentos fallidos: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Error interno del servidor al actualizar intentos de login."
            )

        if user.intentos_fallidos >= MAX_FAILED_ATTEMPTS:
            user.estado = auth_utils.EstadoEnum.bloqueado
            user.bloqueado_hasta = datetime.now(timezone.utc) # Store as timezone-aware
            print(f"DEBUG: ¡Límite de intentos alcanzado! Bloqueando usuario '{user.nombre_usuario}'.")
            print(f"DEBUG: Nuevo estado: {user.estado}, Bloqueado hasta: {user.bloqueado_hasta}")
            try:
                db.add(user)
                db.commit()
                db.refresh(user)
                print(f"DEBUG: Bloqueo de usuario guardado y refrescado. Estado final: {user.estado}")
            except Exception as e:
                db.rollback()
                print(f"ERROR: Fallo al bloquear usuario: {e}")
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Error interno del servidor al bloquear el usuario."
                )

        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credenciales inválidas",
            headers={"WWW-Authenticate": "Bearer"},
        )

    print(f"DEBUG: Contraseña correcta para '{user.nombre_usuario}'.")
    user.intentos_fallidos = 0
    user.bloqueado_hasta = None # Resetting to None is fine, it's naive
    if user.estado == auth_utils.EstadoEnum.bloqueado:
        user.estado = auth_utils.EstadoEnum.activo
        print(f"DEBUG: Usuario '{user.nombre_usuario}' activado después de login exitoso.")

    print(f"DEBUG: Reiniciando intentos fallidos y bloqueo. Nuevos valores: {user.intentos_fallidos}, {user.bloqueado_hasta}, {user.estado}")
    try:
        db.add(user)
        db.commit()
        db.refresh(user)
        print("DEBUG: Cambios de éxito de login guardados y refrescados.")
    except Exception as e:
        db.rollback()
        print(f"ERROR: Fallo al reiniciar intentos fallidos en login exitoso: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error interno del servidor al procesar el login exitoso."
        )

    access_token_expires = timedelta(minutes=auth_utils.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = auth_utils.create_access_token(
        data={"sub": user.nombre_usuario},
        expires_delta=access_token_expires
    )
    print("DEBUG: Token de acceso generado exitosamente.")
    return {"access_token": access_token, "token_type": "bearer"}

# Endpoint para solicitar un código de recuperación de contraseña
@router.post("/forgot-password-request", status_code=status.HTTP_200_OK)
async def forgot_password_request(
    request: ForgotPasswordRequest,
    db: Session = Depends(get_db)
):
    """
    Inicia el proceso de recuperación de contraseña.
    Genera un código, lo almacena y lo envía al correo del usuario.
    """
    user = db.query(auth_utils.Usuario).options(
        joinedload(auth_utils.Usuario.persona)
    ).filter(auth_utils.Usuario.nombre_usuario == request.username_or_email).first()

    if not user:
        persona = db.query(DBPersona).options(
            joinedload(DBPersona.usuario)
        ).filter(DBPersona.email == request.username_or_email).first()
        if persona and persona.usuario:
            user = persona.usuario

    if not user:
        print(f"ADVERTENCIA: Intento de recuperación para usuario/email no encontrado: {request.username_or_email}")
        return {"message": "Si la dirección de correo o el usuario son válidos, se ha enviado un código de recuperación."}

    user_email = user.persona.email if user.persona else None
    if not user_email:
        print(f"ADVERTENCIA: Usuario '{user.nombre_usuario}' no tiene un correo electrónico asociado para recuperación. ID: {user.usuario_id}")
        return {"message": "Si la dirección de correo o el usuario son válidos, se ha enviado un código de recuperación."}

    recovery_code = auth_utils.generate_recovery_code()
    expiration_time = datetime.now(timezone.utc) + timedelta(minutes=auth_utils.RECOVERY_CODE_EXPIRE_MINUTES) # Store as timezone-aware

    user.codigo_recuperacion = recovery_code
    user.expiracion_codigo_recuperacion = expiration_time
    try:
        db.add(user)
        db.commit()
        db.refresh(user)
        print(f"DEBUG: Código de recuperación generado para '{user.nombre_usuario}'. Código: {recovery_code}")
        print(f"DEBUG: Expiración código guardado (desde generación): {user.expiracion_codigo_recuperacion} (tzinfo: {user.expiracion_codigo_recuperacion.tzinfo})") # Añadido
    except Exception as e:
        db.rollback()
        print(f"ERROR: Fallo al guardar código de recuperación para '{user.nombre_usuario}': {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error interno del servidor al procesar la solicitud de recuperación."
        )

    auth_utils.send_recovery_email(user_email, user.nombre_usuario, recovery_code)
    print(f"DEBUG: Correo de recuperación enviado (simulado/real) a {user_email}")

    return {"message": "Si la dirección de correo o el usuario son válidos, se ha enviado un código de recuperación."}

# Endpoint para restablecer la contraseña usando el código
@router.post("/reset-password", status_code=status.HTTP_200_OK)
def reset_password(
    request: ResetPasswordRequest,
    db: Session = Depends(get_db)
):
    """
    Restablece la contraseña de un usuario usando un código de recuperación válido.
    También desbloquea y activa la cuenta si estaba bloqueada/inactiva.
    """
    user = db.query(auth_utils.Usuario).options(
        joinedload(auth_utils.Usuario.persona)
    ).filter(auth_utils.Usuario.nombre_usuario == request.username_or_email).first()

    if not user:
        persona = db.query(DBPersona).options(
            joinedload(DBPersona.usuario)
        ).filter(DBPersona.email == request.username_or_email).first()
        if persona and persona.usuario:
            user = persona.usuario

    if not user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Usuario o correo electrónico no encontrado."
        )

    # --- AÑADE ESTAS LÍNEAS DE DEPURACIÓN AQUÍ ---
    print(f"\n--- DEBUGGING PASSWORD RESET EXPIRATION ---")
    print(f"  Código recibido: {request.recovery_code}")
    print(f"  Código en DB (antes de helper): {user.codigo_recuperacion}")
    print(f"  Expiración en DB (antes de helper): {user.expiracion_codigo_recuperacion} (tzinfo: {user.expiracion_codigo_recuperacion.tzinfo if user.expiracion_codigo_recuperacion else 'None'})")
    # ---------------------------------------------

    # Make user.expiracion_codigo_recuperacion timezone-aware before comparison
    user_expiracion_codigo_recuperacion_aware = make_datetime_utc_aware(user.expiracion_codigo_recuperacion)
    current_utc_time = datetime.now(timezone.utc)

    # --- AÑADE ESTAS LÍNEAS DE DEPURACIÓN AQUÍ ---
    print(f"  Expiración en DB (después de helper): {user_expiracion_codigo_recuperacion_aware} (tzinfo: {user_expiracion_codigo_recuperacion_aware.tzinfo if user_expiracion_codigo_recuperacion_aware else 'None'})")
    print(f"  Tiempo UTC Actual: {current_utc_time} (tzinfo: {current_utc_time.tzinfo})")
    print(f"  ¿current_utc_time > user_expiracion_codigo_recuperacion_aware?: {current_utc_time > (user_expiracion_codigo_recuperacion_aware or datetime.min.replace(tzinfo=timezone.utc))}") # Compara con un mínimo si es None
    # ---------------------------------------------

    if not user.codigo_recuperacion or user.codigo_recuperacion != request.recovery_code:
        print(f"ADVERTENCIA: Intento de reinicio de contraseña fallido para '{user.nombre_usuario}'. Código incorrecto.")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Código de recuperación inválido o usuario/email incorrecto."
        )

    if user_expiracion_codigo_recuperacion_aware is None or current_utc_time > user_expiracion_codigo_recuperacion_aware:
        user.codigo_recuperacion = None
        user.expiracion_codigo_recuperacion = None # This is fine to reset to None (naive)
        db.add(user)
        db.commit()
        print(f"ADVERTENCIA: Intento de reinicio de contraseña fallido para '{user.nombre_usuario}'. Código expirado.")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Código de recuperación expirado o inválido. Por favor, solicita uno nuevo."
        )

    user.contraseña = auth_utils.get_password_hash(request.new_password)

    user.codigo_recuperacion = None
    user.expiracion_codigo_recuperacion = None # This is fine to reset to None (naive)
    user.intentos_fallidos = 0
    user.bloqueado_hasta = None # This is fine to reset to None (naive)
    user.estado = auth_utils.EstadoEnum.activo

    try:
        db.add(user)
        db.commit()
        db.refresh(user)
        print(f"DEBUG: Contraseña de '{user.nombre_usuario}' restablecida exitosamente y cuenta activada.")
    except Exception as e:
        db.rollback()
        print(f"ERROR: Fallo al restablecer la contraseña o actualizar el usuario: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error interno del servidor al restablecer la contraseña."
        )

    return {"message": "Contraseña restablecida exitosamente. Ahora puede iniciar sesión."}

# Endpoint para obtener información del usuario actual (requiere token)
@router.get("/me", response_model=UsuarioReadAudit)
def read_users_me(current_user: auth_utils.Usuario = Depends(auth_utils.get_current_active_user)):
    """
    Obtiene la información del usuario actualmente autenticado.
    """
    return current_user
