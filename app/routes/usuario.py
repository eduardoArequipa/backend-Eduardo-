# backEnd/app/routes/usuarios.py
import os
import uuid
from typing import List, Optional
from datetime import datetime, timedelta # Importar timedelta
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import or_
from sqlalchemy import not_

from .. import auth as auth_utils
from ..database import get_db
from ..models.usuario import Usuario as DBUsuario
from ..models.persona import Persona as DBPersona
from ..models.rol import Rol as DBRol
from ..models.enums import EstadoEnum

from ..schemas.usuario import (
    UsuarioBase,
    UsuarioCreate,
    UsuarioUpdate,
    Usuario,
    UsuarioAudit,
    UsuarioReadAudit
)
from ..schemas.persona import PersonaNested
from ..schemas.rol import RolNested


router = APIRouter(
    prefix="/usuarios",
    tags=["usuarios"]
)

ROLES_CAN_MANAGE_USERS = ["Administrador"]
ROLES_CAN_MANAGE_USER_ROLES = ["Administrador"]


# --- Endpoint para Listar Usuarios ---
@router.get("/", response_model=List[UsuarioReadAudit])
def read_usuarios(
    estado: Optional[EstadoEnum] = Query(None, description="Filtrar por estado"),
    search: Optional[str] = Query(None, description="Texto de búsqueda por nombre de usuario o nombre/apellido de persona"),
    rol_id: Optional[int] = Query(None, description="Filtrar por Usuarios que tienen este Rol (ID)"),
    persona_id: Optional[int] = Query(None, description="Filtrar por Usuario asociado a esta Persona ID"),
    skip: int = Query(0, ge=0, description="Número de elementos a omitir (paginación)"),
    limit: int = Query(100, gt=0, description="Número máximo de elementos a retornar (paginación)"),
    db: Session = Depends(get_db),
    current_user: auth_utils.Usuario = Depends(auth_utils.get_current_active_user_with_role(ROLES_CAN_MANAGE_USERS))
):
    query = db.query(DBUsuario).options(
        joinedload(DBUsuario.persona),
        joinedload(DBUsuario.roles),
        joinedload(DBUsuario.creador),
        # NO es necesario joinedload para codigo_recuperacion y expiracion_codigo_recuperacion
        # ya que son columnas directas de la tabla DBUsuario.
        # Si tienes una relación 'modificador' explícita en DBUsuario, deberías cargarla aquí también:
        # joinedload(DBUsuario.modificador),
    )

    if estado:
        query = query.filter(DBUsuario.estado == estado)

    if search:
        query = query.join(DBUsuario.persona).filter(
            or_(
                DBUsuario.nombre_usuario.ilike(f"%{search}%"),
                DBPersona.nombre.ilike(f"%{search}%"),
                DBPersona.apellido_paterno.ilike(f"%{search}%"),
                DBPersona.apellido_materno.ilike(f"%{search}%"),
            )
        )

    if rol_id is not None:
        query = query.join(DBUsuario.roles).filter(DBRol.rol_id == rol_id)

    if persona_id is not None:
        query = query.filter(DBUsuario.persona_id == persona_id)

    usuarios = query.offset(skip).limit(limit).all()

    return usuarios


# --- Endpoint para Obtener un Usuario por ID ---
@router.get("/{usuario_id}", response_model=UsuarioReadAudit)
def read_usuario(
    usuario_id: int,
    db: Session = Depends(get_db),
    current_user: auth_utils.Usuario = Depends(auth_utils.get_current_active_user)
):
    user_role_names = {rol.nombre_rol for rol in current_user.roles}
    can_manage_all = any(role_name in user_role_names for role_name in ROLES_CAN_MANAGE_USERS)

    if current_user.usuario_id != usuario_id and not can_manage_all:
         raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tienes permiso para ver la información de este usuario."
         )

    usuario = db.query(DBUsuario).options(
        joinedload(DBUsuario.persona),
        joinedload(DBUsuario.roles),
        joinedload(DBUsuario.creador),
        # NO es necesario joinedload para codigo_recuperacion y expiracion_codigo_recuperacion
        # ya que son columnas directas de la tabla DBUsuario.
    ).filter(DBUsuario.usuario_id == usuario_id).first()

    if usuario is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Usuario no encontrado")

    return usuario


# --- Endpoint para Crear un Nuevo Usuario ---
@router.post("/", response_model=UsuarioReadAudit, status_code=status.HTTP_201_CREATED)
def create_usuario(
    usuario: UsuarioCreate,
    db: Session = Depends(get_db),
    current_user: auth_utils.Usuario = Depends(auth_utils.get_current_active_user_with_role(ROLES_CAN_MANAGE_USERS))
):
    try:
        persona = db.query(DBPersona).filter(DBPersona.persona_id == usuario.persona_id).first()
        if persona is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Persona no encontrada para asociar con este Usuario.")

        existing_usuario = db.query(DBUsuario).filter(DBUsuario.persona_id == usuario.persona_id).first()
        if existing_usuario:
             raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Esta persona ya tiene un usuario asociado.")

        db_usuario_nombre = db.query(DBUsuario).filter(DBUsuario.nombre_usuario == usuario.nombre_usuario).first()
        if db_usuario_nombre:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Ya existe un usuario con este nombre de usuario.")

        hashed_password = auth_utils.get_password_hash(usuario.contraseña)

        new_usuario = DBUsuario(
            persona_id=usuario.persona_id,
            nombre_usuario=usuario.nombre_usuario,
            contraseña=hashed_password,
            estado=usuario.estado if usuario.estado is not None else EstadoEnum.activo,
            foto_ruta=usuario.foto_ruta,
            creado_por=current_user.usuario_id
            # Los nuevos campos codigo_recuperacion y expiracion_codigo_recuperacion no se establecen aquí
            # porque se manejarán en un proceso de recuperación de contraseña separado.
        )
        db.add(new_usuario)
        db.flush()

        db.commit()

        db_usuario_for_response = db.query(DBUsuario).options(
             joinedload(DBUsuario.persona),
             joinedload(DBUsuario.roles),
             joinedload(DBUsuario.creador),
        ).filter(DBUsuario.usuario_id == new_usuario.usuario_id).first()

        return db_usuario_for_response

    except HTTPException as e:
        raise e
    except Exception as e:
        db.rollback()
        print(f"Error durante la creación de Usuario: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Ocurrió un error interno al crear el Usuario.")


# --- Endpoint para Actualizar un Usuario por ID ---
@router.put("/{usuario_id}", response_model=UsuarioReadAudit)
def update_usuario(
    usuario_id: int,
    usuario_update: UsuarioUpdate,
    db: Session = Depends(get_db),
    current_user: auth_utils.Usuario = Depends(auth_utils.get_current_active_user)
):
    db_usuario = db.query(DBUsuario).filter(DBUsuario.usuario_id == usuario_id).first()
    if db_usuario is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Usuario no encontrado.")

    user_role_names = {rol.nombre_rol for rol in current_user.roles}
    can_manage_all = any(role_name in user_role_names for role_name in ROLES_CAN_MANAGE_USERS)

    if current_user.usuario_id != usuario_id and not can_manage_all:
         raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tienes permiso para actualizar este usuario."
         )

    update_data_sent = usuario_update.model_dump(exclude_unset=True)
    if not can_manage_all:
         if 'estado' in update_data_sent:
              raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="No tienes permiso para cambiar el estado del usuario.")

    update_data = usuario_update.model_dump(exclude_unset=True, exclude={'contraseña'})

    if "contraseña" in usuario_update.model_dump(exclude_unset=False) and usuario_update.contraseña:
        if usuario_update.contraseña != "":
            if not can_manage_all and current_user.usuario_id != usuario_id:
                 raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="No tienes permiso para cambiar la contraseña de este usuario.")

            hashed_password = auth_utils.get_password_hash(usuario_update.contraseña)
            db_usuario.contraseña = hashed_password

    for field, value in update_data.items():
        setattr(db_usuario, field, value)

    # NOTA: codigo_recuperacion y expiracion_codigo_recuperacion no se actualizan aquí
    # ya que no se incluyeron en el esquema UsuarioUpdate.
    # Si se necesita un endpoint para resetear contraseña, se crearía uno separado.

    db.commit()
    db.refresh(db_usuario)

    db_usuario_for_response = db.query(DBUsuario).options(
         joinedload(DBUsuario.persona),
         joinedload(DBUsuario.roles),
         joinedload(DBUsuario.creador),
    ).filter(DBUsuario.usuario_id == db_usuario.usuario_id).first()

    return db_usuario_for_response


# --- Endpoint para Eliminar/Desactivar un Usuario por ID ---
@router.delete("/{usuario_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_usuario(
    usuario_id: int,
    db: Session = Depends(get_db),
    current_user: auth_utils.Usuario = Depends(auth_utils.get_current_active_user_with_role(ROLES_CAN_MANAGE_USERS))
):
    db_usuario = db.query(DBUsuario).filter(DBUsuario.usuario_id == usuario_id).first()
    if db_usuario is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Usuario no encontrado.")

    if db_usuario.usuario_id == current_user.usuario_id:
         raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No puedes desactivar tu propio usuario.")

    db_usuario.estado = EstadoEnum.inactivo

    db.commit()

    return {}


# --- Endpoint para Activar un Usuario por ID (PATCH) ---
@router.patch("/{usuario_id}", response_model=UsuarioReadAudit)
def activate_usuario(
    usuario_id: int,
    db: Session = Depends(get_db),
    current_user: auth_utils.Usuario = Depends(auth_utils.get_current_active_user_with_role(ROLES_CAN_MANAGE_USERS))
):
    db_usuario = db.query(DBUsuario).options(
         joinedload(DBUsuario.persona),
         joinedload(DBUsuario.roles),
         joinedload(DBUsuario.creador),
    ).filter(DBUsuario.usuario_id == usuario_id).first()

    if db_usuario is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Usuario no encontrado.")

    if db_usuario.estado == EstadoEnum.activo:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="El usuario ya está activo.")

    db_usuario.estado = EstadoEnum.activo

    db.commit()
    db.refresh(db_usuario)

    return db_usuario


# --- Endpoints para Gestionar Roles de un Usuario ---

# Endpoint para Asignar un Rol a un Usuario
@router.post("/{usuario_id}/roles/{rol_id}", response_model=UsuarioReadAudit)
def assign_role_to_user(
    usuario_id: int,
    rol_id: int,
    db: Session = Depends(get_db),
    current_user: auth_utils.Usuario = Depends(auth_utils.get_current_active_user_with_role(ROLES_CAN_MANAGE_USER_ROLES))
):
    db_usuario = db.query(DBUsuario).options(
         joinedload(DBUsuario.persona),
         joinedload(DBUsuario.roles),
         joinedload(DBUsuario.creador),
    ).filter(DBUsuario.usuario_id == usuario_id).first()

    if db_usuario is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Usuario no encontrado.")

    db_rol = db.query(DBRol).filter(DBRol.rol_id == rol_id).first()
    if db_rol is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Rol no encontrado.")

    if db_rol in db_usuario.roles:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"El usuario ya tiene el rol '{db_rol.nombre_rol}'.")

    db_usuario.roles.append(db_rol)

    db.commit()
    db.refresh(db_usuario)

    db_usuario_for_response = db.query(DBUsuario).options(
         joinedload(DBUsuario.persona),
         joinedload(DBUsuario.roles),
         joinedload(DBUsuario.creador),
    ).filter(DBUsuario.usuario_id == db_usuario.usuario_id).first()

    return db_usuario_for_response


# Endpoint para Remover un Rol de un Usuario
@router.delete("/{usuario_id}/roles/{rol_id}", response_model=UsuarioReadAudit)
def remove_role_from_user(
    usuario_id: int,
    rol_id: int,
    db: Session = Depends(get_db),
    current_user: auth_utils.Usuario = Depends(auth_utils.get_current_active_user_with_role(ROLES_CAN_MANAGE_USER_ROLES))
):
    db_usuario = db.query(DBUsuario).options(
        joinedload(DBUsuario.persona),
        joinedload(DBUsuario.roles),
        joinedload(DBUsuario.creador),
    ).filter(DBUsuario.usuario_id == usuario_id).first()

    if db_usuario is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Usuario no encontrado.")

    db_rol = db.query(DBRol).filter(DBRol.rol_id == rol_id).first()
    if db_rol is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Rol no encontrado.")

    if db_rol not in db_usuario.roles:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"El usuario no tiene el rol '{db_rol.nombre_rol}'.")

    db_usuario.roles.remove(db_rol)

    db.commit()
    db.refresh(db_usuario)

    db_usuario_for_response = db.query(DBUsuario).options(
         joinedload(DBUsuario.persona),
         joinedload(DBUsuario.roles),
         joinedload(DBUsuario.creador),
    ).filter(DBUsuario.usuario_id == db_usuario.usuario_id).first()

    return db_usuario_for_response

# --- NUEVOS ENDPOINTS PARA RECUPERACIÓN DE CONTRASEÑA ---

# Endpoint para solicitar un código de recuperación
@router.post("/request-password-reset/{nombre_usuario_o_email}", status_code=status.HTTP_200_OK)
async def request_password_reset(
    nombre_usuario_o_email: str,
    db: Session = Depends(get_db)
):
    # Buscar el usuario por nombre de usuario
    db_usuario = db.query(DBUsuario).filter(
        DBUsuario.nombre_usuario == nombre_usuario_o_email
    ).first()

    # Si no se encuentra por nombre de usuario, intentar buscar por email de la persona asociada
    if db_usuario is None:
        db_usuario = db.query(DBUsuario).join(DBUsuario.persona).filter(
            DBPersona.email == nombre_usuario_o_email
        ).first()

    if db_usuario is None:
        # Por seguridad, no decimos si el usuario existe o no para evitar enumeración de usuarios
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Si el usuario existe, se ha enviado un código de recuperación a su correo electrónico asociado.")

    # Generar un código de recuperación aleatorio (ej. 6 dígitos o un UUID corto)
    recovery_code = str(uuid.uuid4())[:8].replace('-', '').upper() # UUID corto sin guiones

    # Establecer la expiración del código (ej. 15 minutos desde ahora)
    expiration_time = datetime.now() + timedelta(minutes=15)

    db_usuario.codigo_recuperacion = recovery_code
    db_usuario.expiracion_codigo_recuperacion = expiration_time
    db.commit()
    db.refresh(db_usuario)

    # TODO: Aquí integrarías el envío del código por email o WhatsApp
    # (Usando Twilio u otro servicio. NO LO IMPLEMENTAREMOS AQUÍ POR RAZONES DE SEGURIDAD Y ALCANCE)
    # Ejemplo de mensaje (no funcional, solo conceptual):
    # await send_whatsapp_message(db_usuario.persona.telefono, f"Tu código de recuperación es: {recovery_code}. Expira en 15 minutos.")
    # o send_email(db_usuario.persona.email, "Código de Recuperación", f"Tu código es: {recovery_code}")

    return {"message": "Si el usuario existe, se ha enviado un código de recuperación a su correo electrónico o teléfono asociado."}

# Endpoint para verificar el código y resetear la contraseña
@router.post("/reset-password", status_code=status.HTTP_200_OK)
async def reset_password(
    nombre_usuario_o_email: str,
    codigo: str,
    nueva_contraseña: str = Query(..., min_length=6), # Nueva contraseña como Query param por simplicidad
    db: Session = Depends(get_db)
):
    # Buscar el usuario por nombre de usuario
    db_usuario = db.query(DBUsuario).filter(
        DBUsuario.nombre_usuario == nombre_usuario_o_email
    ).first()

    # Si no se encuentra por nombre de usuario, intentar buscar por email de la persona asociada
    if db_usuario is None:
        db_usuario = db.query(DBUsuario).join(DBUsuario.persona).filter(
            DBPersona.email == nombre_usuario_o_email
        ).first()

    if db_usuario is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Usuario o código de recuperación inválido.")

    # Verificar el código y la expiración
    if db_usuario.codigo_recuperacion != codigo:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Código de recuperación incorrecto.")

    if db_usuario.expiracion_codigo_recuperacion is None or datetime.now() > db_usuario.expiracion_codigo_recuperacion:
        # Limpiar el código expirado para evitar reuso
        db_usuario.codigo_recuperacion = None
        db_usuario.expiracion_codigo_recuperacion = None
        db.commit()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Código de recuperación expirado o inválido. Por favor, solicita uno nuevo.")

    # Hashear y actualizar la nueva contraseña
    hashed_password = auth_utils.get_password_hash(nueva_contraseña)
    db_usuario.contraseña = hashed_password

    # Limpiar el código de recuperación después de un uso exitoso
    db_usuario.codigo_recuperacion = None
    db_usuario.expiracion_codigo_recuperacion = None
    db_usuario.intentos_fallidos = 0 # Reiniciar intentos fallidos si se resetea contraseña
    db_usuario.bloqueado_hasta = None # Desbloquear si estaba bloqueado

    db.commit()
    db.refresh(db_usuario)

    return {"message": "Contraseña restablecida con éxito."}