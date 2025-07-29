import os
from datetime import datetime, timedelta, timezone
from typing import Optional, List
import secrets # Importar para generar códigos seguros
import string # Importar para caracteres de código
import smtplib # Para enviar correos (puede requerir configuración de SMTP)
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from sqlalchemy.orm import Session, joinedload # Asegúrate de que joinedload esté importado

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from passlib.context import CryptContext

from .database import get_db
from .models.usuario import Usuario
from .models.persona import Persona # Importamos Persona para joinedload
from .models.enums import EstadoEnum # Importamos el Enum
from .schemas.token import TokenData

# --- CONSTANTE DE EXPIRACIÓN DEL CÓDIGO DE RECUPERACIÓN ---
RECOVERY_CODE_EXPIRE_MINUTES = int(os.getenv("RECOVERY_CODE_EXPIRE_MINUTES", 15))

# Configuración de seguridad
# Asegúrate de que estas variables de entorno estén configuradas en tu archivo .env
SECRET_KEY = os.getenv("SECRET_KEY")
ALGORITHM = os.getenv("ALGORITHM", "HS256") # Default a HS256 si no está en .env
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", 1)) # Default 30 minutos

EMAIL_SENDER = os.getenv("EMAIL_SENDER") # Tu dirección de correo, ej: "tu_correo@gmail.com"
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD") # La contraseña de tu correo o contraseña de aplicación
EMAIL_SMTP_SERVER = os.getenv("EMAIL_SMTP_SERVER", "smtp.gmail.com") # Servidor SMTP, ej: "smtp.gmail.com" para Gmail
EMAIL_SMTP_PORT = int(os.getenv("EMAIL_SMTP_PORT", 587)) # Puerto SMTP (587 para TLS, 465 para SSL)

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# OAuth2 Bearer token (para proteger rutas)
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login") # 'auth/login' es la ruta del endpoint de login

# Funciones de hashing y verificación de contraseñas
def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verifica si una contraseña plana coincide con un hash."""
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password: str) -> str:
    """Genera el hash de una contraseña plana."""
    return pwd_context.hash(password)

# Funciones para crear y manejar tokens JWT
def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    """Crea un token de acceso JWT."""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

# --- Funciones para Recuperación de Contraseña ---
def generate_recovery_code(length: int = 6) -> str:
    """Genera un código de recuperación alfanumérico seguro."""
    characters = string.ascii_letters + string.digits
    return ''.join(secrets.choice(characters) for _ in range(length))

def send_recovery_email(recipient_email: str, username: str, code: str):
    """
    Envía un correo electrónico con el código de recuperación.
    NOTA: Para producción, se recomienda usar un servicio de terceros (SendGrid, Mailgun, etc.)
          o una configuración SMTP más robusta y segura.
    """
    # --- AÑADE ESTAS LÍNEAS DE DEPURACIÓN AQUÍ ---
    print(f"DEBUGGING EMAIL CONFIG:")
    print(f"  EMAIL_SENDER: {EMAIL_SENDER}")
    print(f"  EMAIL_PASSWORD: {'*' * (len(EMAIL_PASSWORD) if EMAIL_PASSWORD else 0)}") # Oculta la contraseña por seguridad
    print(f"  EMAIL_SMTP_SERVER: {EMAIL_SMTP_SERVER}")
    print(f"  EMAIL_SMTP_PORT: {EMAIL_SMTP_PORT}")
    print(f"  Type of EMAIL_SMTP_PORT: {type(EMAIL_SMTP_PORT)}")
    # ----------------------------------------------

    if not EMAIL_SENDER or not EMAIL_PASSWORD:
        print("ADVERTENCIA: Variables de entorno de correo no configuradas (EMAIL_SENDER o EMAIL_PASSWORD). No se enviará el correo de recuperación real.")
        print(f"DEBUG: Correo simulado a {recipient_email} para usuario {username} con código: {code}")
        return

    msg = MIMEMultipart()
    msg['From'] = EMAIL_SENDER
    msg['To'] = recipient_email
    msg['Subject'] = "Código de Recuperación de Contraseña"

    body = f"""
    Hola {username},

    Has solicitado restablecer tu contraseña.
    Tu código de recuperación es: {code}

    Este código expirará en {RECOVERY_CODE_EXPIRE_MINUTES} minutos. Si no solicitaste esto, puedes ignorar este correo.

    Saludos,
    El equipo de tu sistema
    """
    msg.attach(MIMEText(body, 'plain'))

    try:
        with smtplib.SMTP(EMAIL_SMTP_SERVER, EMAIL_SMTP_PORT) as server:
            server.starttls() # Inicia la seguridad TLS
            server.login(EMAIL_SENDER, EMAIL_PASSWORD)
            server.sendmail(EMAIL_SENDER, recipient_email, msg.as_string())
        print(f"DEBUG: Correo de recuperación enviado a {recipient_email}")
    except Exception as e:
        print(f"ERROR: No se pudo enviar el correo de recuperación a {recipient_email}. Error: {e}")
        # En producción, considera logging a un sistema de monitoreo o reintentos

# --- DEPENDENCIAS DE USUARIO Y ROL ---

async def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    """Obtiene el usuario autenticado a partir del token JWT."""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="No se pudieron validar las credenciales",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        # Decodificar el token
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")

        if username is None:
            raise credentials_exception

        token_data = TokenData(username=username)

    except JWTError:
        raise credentials_exception

    # *** CORRECCIÓN CRUCIAL AQUÍ: Cargar las relaciones anidadas correctamente ***
    # Usa joinedload para cargar la persona y luego sus roles en la misma consulta
    user = db.query(Usuario).options(
        joinedload(Usuario.persona).joinedload(Persona.roles) # Cargar roles a través de persona
    ).filter(Usuario.nombre_usuario == token_data.username).first()

    if user is None:
        raise credentials_exception

    return user

def get_current_active_user(current_user: Usuario = Depends(get_current_user)):
    """
    Obtiene el usuario autenticado y verifica que esté activo,
    incluyendo la verificación de bloqueo temporal.
    """
    # 1. Verificar si el usuario está inactivo (por administración)
    if current_user.estado == EstadoEnum.inactivo:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Usuario inactivo")

    # 2. Verificar si el usuario está bloqueado (por intentos fallidos)
    if current_user.estado == EstadoEnum.bloqueado:
        if current_user.bloqueado_hasta and current_user.bloqueado_hasta > datetime.now(timezone.utc):
            remaining_time_seconds = (current_user.bloqueado_hasta - datetime.now(timezone.utc)).total_seconds()
            minutes = int(remaining_time_seconds // 60)
            seconds = int(remaining_time_seconds % 60)
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Usuario bloqueado temporalmente. Inténtelo de nuevo en {minutes} minuto(s) y {seconds} segundo(s)."
            )
        else:
            # Si el estado es 'bloqueado' pero 'bloqueado_hasta' ya pasó,
            # lo ideal es que un login exitoso lo restablezca a 'activo'.
            # Para fines de acceso a rutas protegidas, si está 'bloqueado' y el tiempo pasó
            # pero no ha habido un login exitoso para restablecerlo, asumimos que aún no está "activo"
            # para acceder a rutas protegidas.
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Usuario inactivo o con estado de bloqueo pendiente de reinicio.")

    return current_user

def get_current_active_user_with_role(required_roles: List[str]):
    """
    Dependencia que verifica que el usuario autenticado esté activo y tenga AL MENOS uno
    de los roles requeridos.
    """
    def _get_current_active_user_with_role_inner(
        current_user: Usuario = Depends(get_current_active_user),
        db: Session = Depends(get_db) # Mantener db si hay operaciones adicionales que lo requieran
    ):

        if not current_user.persona:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Error interno: La información de la persona del usuario no se pudo cargar."
            )

        # Acceder a los roles a través de la relación 'persona'
        user_roles_names = [rol.nombre_rol for rol in current_user.persona.roles]

        if not any(role in user_roles_names for role in required_roles):
            # Si el usuario no tiene ninguno de los roles requeridos
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="No tienes permisos suficientes para acceder a este recurso."
            )
        return current_user
    return _get_current_active_user_with_role_inner # Renombrado para evitar conflicto de nombres

# Lista de roles del sistema para facilitar la referencia
ROLES = ["Administrador", "Empleado", "Proveedor", "Cliente"]
ADMIN_ROLES = ["Administrador"] # Roles que tienen permisos de administrador (ej: gestionar usuarios, roles)
EMPLOYEE_ROLES = ["Administrador", "Empleado"] # Roles que tienen permisos de empleado
# Puedes definir otras listas según necesites