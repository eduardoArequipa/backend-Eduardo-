# backEnd/app/routes/auth.py

from datetime import timedelta, datetime, timezone
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel, Field, EmailStr
from sqlalchemy.orm import Session, joinedload # Importar joinedload para cargar relaciones

from .. import auth as auth_utils # Asumimos que auth_utils es app/auth.py
from ..database import get_db
from ..schemas.token import Token
from ..schemas.usuario import UsuarioReadAudit # Usamos este esquema para /me
from ..schemas.menu import MenuInDB
from ..models.persona import Persona as DBPersona # Ya está importado, es correcto
from ..models.usuario import Usuario # Asegúrate de importar el modelo Usuario explícitamente si auth_utils.Usuario es solo un alias
from ..models.menu import Menu as DBMenu
from ..models.rol import Rol as DBRol # Importar Rol
from ..models.enums import EstadoEnum # Asegúrate de que EstadoEnum esté importado correctamente
from ..services.audit_service import AuditService

router = APIRouter(
    prefix="/auth",
    tags=["Auth"]
)

MAX_FAILED_ATTEMPTS = 3
LOCKOUT_TIME_MINUTES = 15

class ForgotPasswordRequest(BaseModel):
    username_or_email: str

class ResetPasswordRequest(BaseModel):
    username_or_email: str
    recovery_code: str
    new_password: str = Field(..., min_length=6, description="La nueva contraseña debe tener al menos 6 caracteres.")

def make_datetime_utc_aware(dt: Optional[datetime]) -> Optional[datetime]:
    """
    Convierte un datetime naive (sin zona horaria) a UTC aware.
    Si ya es aware o None, lo devuelve tal cual.
    """
    if dt and dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt

# Endpoint de login usando form-data
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
    print(f"\n--- Intento de Login para usuario: {form_data.username} ---")

    # Cargar el usuario, incluyendo su persona asociada y sus roles a través de la persona
    # Aquí está la corrección clave:
    user = db.query(Usuario).options( # Usar directamente el modelo Usuario si está importado
        joinedload(Usuario.persona).joinedload(DBPersona.roles).joinedload(DBRol.menus) # <-- ¡CORREGIDO AQUÍ!
    ).filter(Usuario.nombre_usuario == form_data.username).first()

    if not user:
        print(f"DEBUG: Usuario '{form_data.username}' no encontrado.")
        # Log de intento de login con usuario inexistente
        AuditService.log_action(
            db=db,
            tabla="usuarios",
            accion="LOGIN_FAILED",
            valores_despues={
                "usuario_intentado": form_data.username,
                "resultado": "usuario_inexistente",
                "timestamp": datetime.now(timezone.utc).isoformat()
            },
            request=request,
            descripcion=f"Intento de login con usuario inexistente: {form_data.username}"
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credenciales inválidas",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Asegurarse de que el campo `bloqueado_hasta` sea timezone-aware para la comparación
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

    if user.estado != EstadoEnum.activo: # Usa EstadoEnum directamente si lo importaste
         raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Usuario inactivo o bloqueado",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not auth_utils.verify_password(form_data.password, user.contraseña):
        user.intentos_fallidos = (user.intentos_fallidos or 0) + 1
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
            user.estado = EstadoEnum.bloqueado # Usa EstadoEnum directamente
            user.bloqueado_hasta = datetime.now(timezone.utc) + timedelta(minutes=LOCKOUT_TIME_MINUTES) # Almacenar como timezone-aware
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

        # Log de login fallido por contraseña incorrecta
        AuditService.log_action(
            db=db,
            tabla="usuarios",
            accion="LOGIN_FAILED",
            usuario_id=user.usuario_id,
            registro_id=user.usuario_id,
            valores_despues={
                "usuario": user.nombre_usuario,
                "resultado": "contraseña_incorrecta",
                "intentos_fallidos": user.intentos_fallidos,
                "timestamp": datetime.now(timezone.utc).isoformat()
            },
            request=request,
            descripcion=f"Login fallido: contraseña incorrecta para {user.nombre_usuario}"
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credenciales inválidas",
            headers={"WWW-Authenticate": "Bearer"},
        )

    print(f"DEBUG: Contraseña correcta para '{user.nombre_usuario}'.")
    user.intentos_fallidos = 0
    user.bloqueado_hasta = None # Reiniciar a None es correcto
    if user.estado == EstadoEnum.bloqueado: # Usa EstadoEnum directamente
        user.estado = EstadoEnum.activo # Usa EstadoEnum directamente
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

    # Ahora obtén los roles de la persona asociada al usuario
    # El objeto `user` ya debería tener `persona` y `persona.roles` cargados debido al joinedload inicial
    user_roles = [rol.nombre_rol for rol in user.persona.roles] if user.persona and user.persona.roles else []
    print(f"DEBUG: Roles obtenidos para '{user.nombre_usuario}': {user_roles}")


    access_token_expires = timedelta(minutes=auth_utils.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = auth_utils.create_access_token(
        # Incluye los roles en el token JWT
        data={"sub": user.nombre_usuario, "roles": user_roles},
        expires_delta=access_token_expires
    )
    # Log de login exitoso
    AuditService.log_login(
        db=db,
        usuario_id=user.usuario_id,
        request=request,
        success=True
    )

    print("DEBUG: Token de acceso generado exitosamente.")
    return {"access_token": access_token, "token_type": "bearer"}

# Endpoint para obtener los menús del usuario actual
@router.get("/me/menus", response_model=List[MenuInDB])
def read_user_menus(
    current_user: auth_utils.Usuario = Depends(auth_utils.get_current_active_user)
):
    """
    Obtiene la lista de menús a los que el usuario autenticado tiene acceso
    basado en sus roles.
    """
    if not current_user.persona or not current_user.persona.roles:
        return []

    # Usar un set para evitar menús duplicados si un usuario tiene múltiples roles
    # que dan acceso al mismo menú.
    user_menus = {menu for rol in current_user.persona.roles for menu in rol.menus}
    
    # Ordenar los menús por ID para una presentación consistente
    sorted_menus = sorted(list(user_menus), key=lambda menu: menu.menu_id)
    
    print(f"[DEBUG BACKEND] Usuario '{current_user.nombre_usuario}' tiene acceso a {len(sorted_menus)} menús: {[menu.nombre for menu in sorted_menus]}")
    
    return sorted_menus

@router.get("/me/menus-with-roles")
def read_user_menus_with_roles(
    db: Session = Depends(get_db),
    current_user: auth_utils.Usuario = Depends(auth_utils.get_current_active_user)
):
    """
    Obtiene la lista de menús con información de roles para filtrado dinámico.
    Devuelve todos los menús accesibles con la relación rol_menu incluida.
    """
    if not current_user.persona or not current_user.persona.roles:
        return []

    # Obtener todos los IDs de roles del usuario
    user_role_ids = [rol.rol_id for rol in current_user.persona.roles]

    # Buscar todos los menús que tienen relación con estos roles
    from ..models.menu import Menu
    from ..models.rol_menu import RolMenu
    from ..models.rol import Rol
    from sqlalchemy.orm import joinedload

    # Query que trae menús con sus relaciones rol_menus precargadas
    menus_query = db.query(Menu).options(
        joinedload(Menu.rol_menus).joinedload(RolMenu.rol)
    ).join(RolMenu, Menu.menu_id == RolMenu.menu_id).filter(
        RolMenu.rol_id.in_(user_role_ids)
    ).distinct()

    menus = menus_query.all()

    # Convertir a diccionarios serializables
    result = []
    for menu in menus:
        menu_dict = {
            "menu_id": menu.menu_id,
            "nombre": menu.nombre,
            "ruta": menu.ruta,
            "descripcion": menu.descripcion,
            "icono": menu.icono,
            "rol_menu": [
                {
                    "rol": {
                        "rol_id": rm.rol.rol_id,
                        "nombre_rol": rm.rol.nombre_rol
                    }
                }
                for rm in menu.rol_menus
            ]
        }
        result.append(menu_dict)

    # Ordenar por menu_id
    result.sort(key=lambda m: m["menu_id"])

    print(f"[DEBUG] Usuario '{current_user.nombre_usuario}' - Menús con roles: {len(result)}")

    return result

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
    # Buscar usuario por nombre de usuario
    user = db.query(Usuario).options( # Usar directamente Usuario
        joinedload(Usuario.persona) # Cargar la persona asociada
    ).filter(Usuario.nombre_usuario == request.username_or_email).first()

    # Si no se encuentra por nombre de usuario, buscar por email de la persona asociada
    if not user:
        persona = db.query(DBPersona).options(
            joinedload(DBPersona.usuario) # Cargar el usuario asociado a la persona
        ).filter(DBPersona.email == request.username_or_email).first()
        if persona and persona.usuario:
            user = persona.usuario

    if not user:
        print(f"ADVERTENCIA: Intento de recuperación para usuario/email no encontrado: {request.username_or_email}")
        # Se devuelve un mensaje genérico por seguridad para no revelar si el usuario existe o no
        return {"message": "Si la dirección de correo o el usuario son válidos, se ha enviado un código de recuperación."}

    # Asegurarse de que la persona tenga un email antes de intentar enviar
    user_email = user.persona.email if user.persona else None
    if not user_email:
        print(f"ADVERTENCIA: Usuario '{user.nombre_usuario}' no tiene un correo electrónico asociado para recuperación. ID: {user.usuario_id}")
        return {"message": "Si la dirección de correo o el usuario son válidos, se ha enviado un código de recuperación."}

    recovery_code = auth_utils.generate_recovery_code()
    expiration_time = datetime.now(timezone.utc) + timedelta(minutes=auth_utils.RECOVERY_CODE_EXPIRE_MINUTES) # Almacenar como timezone-aware

    user.codigo_recuperacion = recovery_code
    user.expiracion_codigo_recuperacion = expiration_time
    try:
        db.add(user)
        db.commit()
        db.refresh(user)
        print(f"DEBUG: Código de recuperación generado para '{user.nombre_usuario}'. Código: {recovery_code}")
        print(f"DEBUG: Expiración código guardado (desde generación): {user.expiracion_codigo_recuperacion} (tzinfo: {user.expiracion_codigo_recuperacion.tzinfo})")
    except Exception as e:
        db.rollback()
        print(f"ERROR: Fallo al guardar código de recuperación para '{user.nombre_usuario}': {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error interno del servidor al procesar la solicitud de recuperación."
        )

    # Aquí iría la lógica para enviar el email real
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
    # Buscar usuario por nombre de usuario
    user = db.query(Usuario).options( # Usar directamente Usuario
        joinedload(Usuario.persona) # Cargar la persona asociada
    ).filter(Usuario.nombre_usuario == request.username_or_email).first()

    # Si no se encuentra por nombre de usuario, buscar por email de la persona asociada
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

    # --- LÍNEAS DE DEPURACIÓN ---
    print(f"\n--- DEBUGGING PASSWORD RESET EXPIRATION ---")
    print(f"  Código recibido: {request.recovery_code}")
    print(f"  Código en DB (antes de helper): {user.codigo_recuperacion}")
    print(f"  Expiración en DB (antes de helper): {user.expiracion_codigo_recuperacion} (tzinfo: {user.expiracion_codigo_recuperacion.tzinfo if user.expiracion_codigo_recuperacion else 'None'})")
    # ---------------------------------------------

    # Asegurarse de que el campo `expiracion_codigo_recuperacion` sea timezone-aware
    user_expiracion_codigo_recuperacion_aware = make_datetime_utc_aware(user.expiracion_codigo_recuperacion)
    current_utc_time = datetime.now(timezone.utc)

    # --- LÍNEAS DE DEPURACIÓN ---
    print(f"  Expiración en DB (después de helper): {user_expiracion_codigo_recuperacion_aware} (tzinfo: {user_expiracion_codigo_recuperacion_aware.tzinfo if user_expiracion_codigo_recuperacion_aware else 'None'})")
    print(f"  Tiempo UTC Actual: {current_utc_time} (tzinfo: {current_utc_time.tzinfo})")
    print(f"  ¿current_utc_time > user_expiracion_codigo_recuperacion_aware?: {current_utc_time > (user_expiracion_codigo_recuperacion_aware or datetime.min.replace(tzinfo=timezone.utc))}")
    # ---------------------------------------------

    if not user.codigo_recuperacion or user.codigo_recuperacion != request.recovery_code:
        print(f"ADVERTENCIA: Intento de reinicio de contraseña fallido para '{user.nombre_usuario}'. Código incorrecto.")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Código de recuperación inválido o usuario/email incorrecto."
        )

    if user_expiracion_codigo_recuperacion_aware is None or current_utc_time > user_expiracion_codigo_recuperacion_aware:
        # Si el código expiró o es nulo (ya usado/no generado), se limpia y se informa
        user.codigo_recuperacion = None
        user.expiracion_codigo_recuperacion = None # Esto es correcto para reiniciar a None (naive o no)
        try:
            db.add(user)
            db.commit()
        except Exception as e:
            db.rollback()
            print(f"ERROR: Fallo al limpiar código expirado para '{user.nombre_usuario}': {e}")
        print(f"ADVERTENCIA: Intento de reinicio de contraseña fallido para '{user.nombre_usuario}'. Código expirado.")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Código de recuperación expirado o inválido. Por favor, solicita uno nuevo."
        )

    user.contraseña = auth_utils.get_password_hash(request.new_password)

    # Reiniciar campos de recuperación y estado de bloqueo
    user.codigo_recuperacion = None
    user.expiracion_codigo_recuperacion = None # Esto es correcto para reiniciar a None
    user.intentos_fallidos = 0
    user.bloqueado_hasta = None # Esto es correcto para reiniciar a None
    user.estado = EstadoEnum.activo # Asegurarse de que el usuario esté activo

    try:
        db.add(user)
        db.commit()
        db.refresh(user)
        print(f"DEBUG: Contraseña de '{user.nombre_usuario}' restablecida exitosamente y cuenta activada.")
    except Exception as e:
        db.rollback()
        
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
    Esta función depende de que `auth_utils.get_current_active_user`
    cargue correctamente las relaciones `persona` y `roles` del usuario.
    """
    return current_user