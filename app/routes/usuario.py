# backEnd/app/routes/usuario.py

from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query, Path, Response
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import or_

from .. import auth as auth_utils
from ..database import get_db
from ..models.usuario import Usuario as DBUsuario # Alias para el modelo de la BD
from ..models.persona import Persona as DBPersona # Importar Persona
from ..models.rol import Rol as DBRol # Importar Rol
from ..models.enums import EstadoEnum
from ..schemas.usuario import UsuarioCreate, UsuarioUpdate, UsuarioReadAudit, Usuario as UsuarioSchema # Importamos los esquemas

router = APIRouter(
    prefix="/usuarios",
    tags=["usuarios"]
)

# Roles de USUARIO que tienen permiso para gestionar otros usuarios (CRUD básico de usuarios)
ROLES_CAN_MANAGE_USERS = ["Administrador"]
# Roles de USUARIO que tienen permiso para asignar/quitar roles a otros usuarios
ROLES_CAN_MANAGE_USER_ROLES = ["Administrador"]

# --- Dependencias Reutilizables ---
def get_usuario_or_404(
    usuario_id: int = Path(..., title="El ID del usuario"),
    db: Session = Depends(get_db)
) -> DBUsuario:
    """
    Dependencia para obtener un usuario por ID con sus relaciones precargadas (persona, roles de LA PERSONA, creador).
    Lanza un error 404 si no se encuentra.
    """
    # Cargamos eager loading para las relaciones clave: Usuario.persona y Persona.roles
    usuario = db.query(DBUsuario).options(
        joinedload(DBUsuario.persona).joinedload(DBPersona.roles), # CORRECCIÓN: Los roles están en Persona
        joinedload(DBUsuario.creador)  # Carga el Usuario que lo creó (para auditoría)
    ).filter(DBUsuario.usuario_id == usuario_id).first()

    if usuario is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Usuario no encontrado.")
    return usuario

# --- Rutas de API para Usuarios ---

@router.get("/", response_model=List[UsuarioReadAudit])
def read_usuarios(
    estado: Optional[EstadoEnum] = Query(None, description="Filtrar por estado del usuario"),
    search: Optional[str] = Query(None, description="Buscar por nombre de usuario, nombre de persona o apellido de persona."),
    # Filtrar por rol_id: se refiere a los roles de LA PERSONA asociada al usuario
    rol_id: Optional[int] = Query(None, description="Filtrar por ID de Rol de la Persona asociada al Usuario"),
    skip: int = Query(0, ge=0), limit: int = Query(100, gt=0),
    db: Session = Depends(get_db),
    current_user: auth_utils.Usuario = Depends(auth_utils.get_current_active_user_with_role(ROLES_CAN_MANAGE_USERS))
):
    """
    Obtiene una lista de usuarios, con opciones de filtrado y búsqueda.
    Solo accesible para usuarios con roles de gestión de usuarios.
    """
    query = db.query(DBUsuario).options(
        joinedload(DBUsuario.persona).joinedload(DBPersona.roles), # CORRECCIÓN: Carga los roles a través de la persona
        joinedload(DBUsuario.creador)
    )
    
    if estado:
        query = query.filter(DBUsuario.estado == estado)
    
    if search:
        # Se une a Persona para buscar en sus campos también
        query = query.join(DBUsuario.persona).filter(or_(
            DBUsuario.nombre_usuario.ilike(f"%{search}%"),
            DBPersona.nombre.ilike(f"%{search}%"),
            DBPersona.apellido_paterno.ilike(f"%{search}%"),
            DBPersona.apellido_materno.ilike(f"%{search}%")
        ))
    
    if rol_id is not None:
        # CORRECCIÓN: Se une a la relación de roles de la PERSONA del usuario
        query = query.join(DBUsuario.persona).join(DBPersona.roles).filter(DBRol.rol_id == rol_id)
    
    return query.order_by(DBUsuario.usuario_id.desc()).offset(skip).limit(limit).all()

@router.get("/{usuario_id}", response_model=UsuarioReadAudit)
def read_usuario(
    usuario: DBUsuario = Depends(get_usuario_or_404),
    current_user: auth_utils.Usuario = Depends(auth_utils.get_current_active_user)
):
    """
    Obtiene los detalles de un usuario específico.
    Solo el Administrador o el propio usuario pueden ver su perfil.
    """
    # CORRECCIÓN: Acceder a los roles de la persona del usuario actual
    user_roles = {rol.nombre_rol for rol in current_user.persona.roles}
    is_admin = "Administrador" in user_roles
    
    # Permiso: Si no es admin y no es su propio perfil, prohíbe el acceso
    if not is_admin and current_user.usuario_id != usuario.usuario_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="No tienes permiso para ver este usuario.")
    
    return usuario

@router.post("/", response_model=UsuarioSchema, status_code=status.HTTP_201_CREATED)
def create_usuario(
    usuario_create: UsuarioCreate,
    db: Session = Depends(get_db),
    current_user: auth_utils.Usuario = Depends(auth_utils.get_current_active_user_with_role(ROLES_CAN_MANAGE_USERS))
):
    """
    Crea un nuevo usuario vinculado a una persona existente.
    Solo accesible para usuarios con roles de gestión de usuarios (Administrador).
    """
    db.begin_nested() # Inicia una transacción anidada
    try:
        # 1. Verificar si la Persona existe y cargar sus roles
        persona = db.query(DBPersona).options(
            joinedload(DBPersona.roles) # Necesario para validar roles de la persona
        ).filter(DBPersona.persona_id == usuario_create.persona_id).first()
        if not persona:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="La Persona especificada para asociar no fue encontrada.")
        
        # 2. Verificar si la Persona ya tiene un usuario
        if db.query(DBUsuario).filter(DBUsuario.persona_id == usuario_create.persona_id).first():
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Esta Persona ya tiene un usuario asociado.")
        
        # 3. Verificar unicidad del nombre de usuario
        if db.query(DBUsuario).filter(DBUsuario.nombre_usuario == usuario_create.nombre_usuario).first():
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Ya existe un usuario con este nombre de usuario.")

        # 4. Validar que los roles de la Persona permitan tener un Usuario
        # Obtener los nombres de roles de la persona
        persona_role_names = {rol.nombre_rol for rol in persona.roles}
        # Verificar si la persona tiene un rol que le permita ser usuario del sistema
        if not any(role_name in persona_role_names for role_name in ["Administrador", "Empleado"]):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Solo personas con roles 'Administrador' o 'Empleado' pueden tener una cuenta de usuario."
            )

        # 5. Hashear la contraseña y crear el usuario
        hashed_password = auth_utils.get_password_hash(usuario_create.contraseña)
        new_usuario = DBUsuario(
            **usuario_create.model_dump(exclude={'contraseña'}),
            hashed_password=hashed_password, # CORRECCIÓN: Usar hashed_password
            creado_por=current_user.usuario_id # Auditoría: quién lo creó
        )
        
        db.add(new_usuario)
        db.commit() # Confirma la creación del usuario
        db.refresh(new_usuario) # Refresca para cargar las relaciones, como 'persona'
        
        return new_usuario
    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Ocurrió un error inesperado al crear el Usuario: {str(e)}")

@router.put("/{usuario_id}", response_model=UsuarioReadAudit)
def update_usuario(
    usuario_update: UsuarioUpdate,
    db_usuario: DBUsuario = Depends(get_usuario_or_404),
    db: Session = Depends(get_db),
    current_user: auth_utils.Usuario = Depends(auth_utils.get_current_active_user)
):
    """
    Actualiza los datos de un usuario.
    Permite a un Administrador actualizar cualquier usuario, y al propio usuario actualizar su perfil (excepto el estado).
    """
    # CORRECCIÓN: Acceder a los roles de la persona del usuario actual
    is_admin = "Administrador" in {rol.nombre_rol for rol in current_user.persona.roles}
    is_owner = current_user.usuario_id == db_usuario.usuario_id

    if not is_admin and not is_owner:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="No tienes permiso para actualizar este usuario.")

    update_data = usuario_update.model_dump(exclude_unset=True) # Solo los campos que se enviaron

    # Control de permiso para cambiar el estado
    if 'estado' in update_data and not is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="No tienes permiso para cambiar el estado del usuario.")
    
    # Manejo de la contraseña
    if 'contraseña' in update_data and update_data['contraseña'] is not None:
        db_usuario.contraseña = auth_utils.get_password_hash(update_data['contraseña'])
        del update_data['contraseña'] # Eliminar del diccionario para que el bucle no la procese
    
    # Actualizar nombre de usuario si es diferente y único (si no es el propio usuario, o si es un cambio crítico)
    if 'nombre_usuario' in update_data and update_data['nombre_usuario'] != db_usuario.nombre_usuario:
        if db.query(DBUsuario).filter(DBUsuario.nombre_usuario == update_data['nombre_usuario'], DBUsuario.usuario_id != db_usuario.usuario_id).first():
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Ya existe un usuario con este nombre de usuario.")

    # Aplicar el resto de los cambios
    for field, value in update_data.items():
        setattr(db_usuario, field, value)
    
    db.commit()
    db.refresh(db_usuario) # Refrescar para cargar las relaciones actualizadas
    return db_usuario

@router.delete("/{usuario_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_usuario(
    db_usuario: DBUsuario = Depends(get_usuario_or_404),
    db: Session = Depends(get_db),
    current_user: auth_utils.Usuario = Depends(auth_utils.get_current_active_user_with_role(ROLES_CAN_MANAGE_USERS))
):
    """
    Desactiva (borrado lógico) un usuario por su ID.
    Solo Administradores pueden desactivar usuarios. Un usuario no puede desactivarse a sí mismo.
    """
    if db_usuario.usuario_id == current_user.usuario_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No puedes desactivar tu propio usuario.")
    if db_usuario.estado == EstadoEnum.inactivo:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="El usuario ya está inactivo.")
    
    db_usuario.estado = EstadoEnum.inactivo
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)

@router.patch("/{usuario_id}/activar", response_model=UsuarioReadAudit)
def activate_usuario(
    db_usuario: DBUsuario = Depends(get_usuario_or_404),
    db: Session = Depends(get_db),
    current_user: auth_utils.Usuario = Depends(auth_utils.get_current_active_user_with_role(ROLES_CAN_MANAGE_USERS))
):
    """
    Activa el estado de un usuario.
    Solo Administradores pueden activar usuarios.
    """
    if db_usuario.estado == EstadoEnum.activo:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="El usuario ya está activo.")
    
    db_usuario.estado = EstadoEnum.activo
    db.commit()
    db.refresh(db_usuario)
    return db_usuario

# --- Rutas para la gestión de Roles de USUARIO ---
# NOTA: Estas rutas asignan/quitan ROLES a la entidad PERSONA del usuario.
# La tabla de asociación es entre PERSONA y ROL.
@router.post("/{usuario_id}/roles/{rol_id}", response_model=UsuarioSchema)
def assign_role_to_user(
    rol_id: int = Path(..., title="ID del Rol a asignar a la Persona del usuario"),
    db_usuario: DBUsuario = Depends(get_usuario_or_404),
    db: Session = Depends(get_db),
    current_user: auth_utils.Usuario = Depends(auth_utils.get_current_active_user_with_role(ROLES_CAN_MANAGE_USER_ROLES))
):
    """
    Asigna un rol específico a la PERSONA asociada a un usuario.
    Solo accesible para usuarios con roles de gestión de roles de usuario (Administrador).
    """
    db_rol = db.query(DBRol).filter(DBRol.rol_id == rol_id).first()
    if not db_rol:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Rol no encontrado.")
    
    if not db_usuario.persona:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="El usuario no tiene una persona asociada.")

    if db_rol in db_usuario.persona.roles: # CORRECCIÓN: Verifica en los roles de la PERSONA
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="La persona del usuario ya tiene este rol asignado.")
    
    db_usuario.persona.roles.append(db_rol) # CORRECCIÓN: Añade el rol a la PERSONA del usuario
    db.commit()
    db.refresh(db_usuario) # Refresca para cargar los roles actualizados
    return db_usuario

@router.delete("/{usuario_id}/roles/{rol_id}", response_model=UsuarioSchema)
def remove_role_from_user(
    rol_id: int = Path(..., title="ID del Rol a remover de la Persona del usuario"),
    db_usuario: DBUsuario = Depends(get_usuario_or_404),
    db: Session = Depends(get_db),
    current_user: auth_utils.Usuario = Depends(auth_utils.get_current_active_user_with_role(ROLES_CAN_MANAGE_USER_ROLES))
):
    """
    Remueve un rol específico de la PERSONA asociada a un usuario.
    Solo accesible para usuarios con roles de gestión de roles de usuario (Administrador).
    """
    db_rol = db.query(DBRol).filter(DBRol.rol_id == rol_id).first()
    if not db_rol:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Rol no encontrado.")
    
    if not db_usuario.persona:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="El usuario no tiene una persona asociada.")

    if db_rol not in db_usuario.persona.roles: # CORRECCIÓN: Verifica en los roles de la PERSONA
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="La persona del usuario no tiene este rol asignado.")

    db_usuario.persona.roles.remove(db_rol) # CORRECCIÓN: Remueve el rol de la PERSONA del usuario
    db.commit()
    db.refresh(db_usuario) # Refresca para cargar los roles actualizados
    return db_usuario