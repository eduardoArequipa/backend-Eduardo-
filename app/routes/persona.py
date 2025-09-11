# backEnd/app/routes/persona.py

from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query, Path, Response
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import or_, not_

from .. import auth as auth_utils
from ..database import get_db
from ..models.persona import Persona as DBPersona
from ..models.usuario import Usuario as DBUsuario
from ..models.rol import Rol as DBRol
from ..models.enums import EstadoEnum, GeneroEnum
# Importamos los esquemas actualizados
from ..schemas.persona import PersonaWithRoles, PersonaCreate, PersonaUpdate, PersonaNested, PersonaPagination # <-- ¡CAMBIO AQUÍ! (PersonaPagination)
from ..schemas.usuario import UsuarioCreate as UsuarioCreateSchemaForPersona # <-- ¡NUEVO! (Para la creación de usuario anidada)

router = APIRouter(
    prefix="/personas",
    tags=["personas"]
)

# Roles que pueden gestionar personas (crear, editar, eliminar)
ROLES_CAN_MANAGE_PERSONS = ["Administrador", "Empleado"] # Estos son roles de USUARIO

# --- Dependencias Reutilizables ---
def get_persona_or_404(
    persona_id: int = Path(..., title="El ID de la persona"),
    db: Session = Depends(get_db)
) -> DBPersona:
    """
    Dependencia para obtener una persona por su ID, incluyendo sus roles de persona.
    Lanza un error 404 si no se encuentra.
    """
    # Cargamos eager loading para la relación de roles de persona
    persona = db.query(DBPersona).options(joinedload(DBPersona.roles), joinedload(DBPersona.usuario)).filter(DBPersona.persona_id == persona_id).first()
    if persona is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Persona no encontrada.")
    return persona

# --- Rutas de API para Personas ---

@router.post("/", response_model=PersonaWithRoles, status_code=status.HTTP_201_CREATED) # <-- ¡CAMBIO AQUÍ! (response_model)
def create_persona(
    persona: PersonaCreate,
    db: Session = Depends(get_db),
    # Solo usuarios con los roles especificados pueden crear personas
    current_user: auth_utils.Usuario = Depends(auth_utils.require_menu_access("/personas")) # Verificar acceso al menú de categorías
):
    db.begin_nested() # Inicia una transacción anidada para rollback en caso de error
    try:
        # 1. Validar unicidad de CI y Email antes de crear la persona
        if persona.ci:
            existing_persona_ci = db.query(DBPersona).filter(DBPersona.ci == persona.ci).first()
            if existing_persona_ci:
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"Ya existe una persona con el CI '{persona.ci}'.")
        if persona.email:
            existing_persona_email = db.query(DBPersona).filter(DBPersona.email == persona.email).first()
            if existing_persona_email:
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"Ya existe una persona con el email '{persona.email}'.")

        # 2. Crear la nueva Persona
        # Excluimos 'usuario_data' y 'rol_ids' del diccionario para la creación directa de DBPersona
        persona_data_dict = persona.model_dump(exclude={'usuario_data', 'rol_ids'}, exclude_unset=True)
        new_persona = DBPersona(**persona_data_dict)

        # 3. Asignar roles de persona (desde PersonaCreate.rol_ids)
        if persona.rol_ids:
            # Filtramos los roles que existen en la base de datos
            roles_to_assign = db.query(DBRol).filter(DBRol.rol_id.in_(persona.rol_ids)).all()
            # Verificamos que todos los IDs de rol proporcionados sean válidos
            if len(roles_to_assign) != len(persona.rol_ids):
                # Identificamos qué roles no se encontraron para un mensaje de error más específico
                found_role_ids = {r.rol_id for r in roles_to_assign}
                invalid_role_ids = set(persona.rol_ids) - found_role_ids
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Uno o más IDs de rol de persona no son válidos: {list(invalid_role_ids)}"
                )
            new_persona.roles.extend(roles_to_assign) # Añadimos los roles a la persona

        db.add(new_persona) # Agregamos la persona a la sesión
        db.flush() # Forzamos la obtención del persona_id antes de crear el usuario

        # 4. Crear Usuario asociado si 'usuario_data' fue proporcionado
        if persona.usuario_data:
            # Validar que los roles de persona de la nueva_persona permitan ser usuario del sistema
            # Esto es una lógica de negocio clave: solo 'Administrador' o 'Empleado' pueden tener un usuario.
            persona_role_names = {rol.nombre_rol for rol in new_persona.roles}
            if not any(role_name in persona_role_names for role_name in ROLES_CAN_MANAGE_PERSONS):
                 raise HTTPException(
                     status_code=status.HTTP_400_BAD_REQUEST,
                     detail="Solo personas con los roles 'Administrador' o 'Empleado' pueden tener una cuenta de usuario."
                 )

            usuario_data: UsuarioCreateSchemaForPersona = persona.usuario_data
            
            # Validar unicidad del nombre de usuario
            if db.query(DBUsuario).filter(DBUsuario.nombre_usuario == usuario_data.nombre_usuario).first():
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Ya existe un usuario con este nombre de usuario.")
            
            # Hashear la contraseña
            hashed_password = auth_utils.get_password_hash(usuario_data.contraseña)
            
            # Crear el nuevo Usuario
            new_usuario = DBUsuario(
                persona_id=new_persona.persona_id,
                nombre_usuario=usuario_data.nombre_usuario,
                contraseña=hashed_password,
                estado=usuario_data.estado,
                foto_ruta=usuario_data.foto_ruta,
                creado_por=current_user.usuario_id
            )
            db.add(new_usuario)

        db.commit()
        db.refresh(new_persona)
        return new_persona

    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Ocurrió un error inesperado al crear la Persona: {str(e)}")


@router.get("/", response_model=PersonaPagination)
def read_personas(
    estado: Optional[EstadoEnum] = Query(None, description="Filtrar por estado"),
    genero: Optional[GeneroEnum] = Query(None, description="Filtrar por género"),
    search: Optional[str] = Query(None, description="Buscar por nombre, CI, email, etc."),
    rol_nombre: Optional[str] = Query(None, description="Filtrar por nombre de rol de persona (ej. 'Cliente')"),
    exclude_rol_nombre: Optional[str] = Query(None, description="Excluir personas que tengan un rol específico"),
    persona_id: Optional[int] = Query(None, description="Obtener una persona por su ID específico"),
    skip: int = Query(0, ge=0), limit: int = Query(100, gt=0),
    db: Session = Depends(get_db),
    current_user: auth_utils.Usuario = Depends(auth_utils.require_menu_access("/personas"))
):
    query = db.query(DBPersona).options(joinedload(DBPersona.roles), joinedload(DBPersona.usuario))

    if persona_id is not None:
        query = query.filter(DBPersona.persona_id == persona_id)
    else:
        if rol_nombre:
            query = query.join(DBPersona.roles).filter(DBRol.nombre_rol.ilike(f"%{rol_nombre}%"))

        if exclude_rol_nombre:
            subquery = db.query(DBPersona.persona_id).join(DBPersona.roles).filter(DBRol.nombre_rol.ilike(f"%{exclude_rol_nombre}%"))
            query = query.filter(DBPersona.persona_id.not_in(subquery))

        if estado:
            query = query.filter(DBPersona.estado == estado)
        if genero:
            query = query.filter(DBPersona.genero == genero)
        
        if search:
            search_pattern = f"%{search}%"
            query = query.filter(or_(
                DBPersona.nombre.ilike(search_pattern),
                DBPersona.apellido_paterno.ilike(search_pattern),
                DBPersona.apellido_materno.ilike(search_pattern),
                DBPersona.ci.ilike(search_pattern),
                DBPersona.email.ilike(search_pattern)
            ))
    
    total = query.count()
    personas = query.order_by(DBPersona.persona_id.desc()).offset(skip).limit(limit).all()

    return {"items": personas, "total": total}

@router.get("/without-user/", response_model=List[PersonaNested])
def read_personas_without_user(
    db: Session = Depends(get_db),
    current_user: auth_utils.Usuario = Depends(auth_utils.require_menu_access("/personas")) # Verificar acceso al menú de categorías
):
    """
    Obtiene una lista de personas que actualmente no tienen una cuenta de usuario asociada.
    Útil para asignar usuarios a personas existentes.
    """
    return db.query(DBPersona).filter(not_(DBPersona.usuario.has())).all()


@router.get("/{persona_id}", response_model=PersonaWithRoles) # <-- ¡CAMBIO AQUÍ! (response_model)
def read_persona(
    persona: DBPersona = Depends(get_persona_or_404), # La dependencia ya carga los roles
    current_user: auth_utils.Usuario = Depends(auth_utils.require_menu_access("/personas")) # Verificar acceso al menú de categorías
):
    """
    Obtiene los detalles de una persona específica por su ID, incluyendo sus roles.
    """
    return persona

@router.put("/{persona_id}", response_model=PersonaWithRoles) # <-- ¡CAMBIO AQUÍ! (response_model)
def update_persona(
    persona_update: PersonaUpdate,
    db_persona: DBPersona = Depends(get_persona_or_404), # La dependencia ya carga los roles
    db: Session = Depends(get_db),
    current_user: auth_utils.Usuario = Depends(auth_utils.require_menu_access("/personas")) # Verificar acceso al menú de categorías
):
    db.begin_nested()
    try:
        # 1. Validar CI y Email si han cambiado (unicidad)
        if persona_update.ci and persona_update.ci != db_persona.ci:
            if db.query(DBPersona).filter(DBPersona.ci == persona_update.ci, DBPersona.persona_id != db_persona.persona_id).first():
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"El CI '{persona_update.ci}' ya está en uso por otra persona.")
        if persona_update.email and persona_update.email != db_persona.email:
            if db.query(DBPersona).filter(DBPersona.email == persona_update.email, DBPersona.persona_id != db_persona.persona_id).first():
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"El email '{persona_update.email}' ya está en uso por otra persona.")

        # 2. Actualizar los campos directos de la Persona
        # Excluimos 'rol_ids' de los datos a actualizar directamente en el modelo DBPersona
        update_data = persona_update.model_dump(exclude_unset=True, exclude={'rol_ids'})
        for field, value in update_data.items():
            setattr(db_persona, field, value)
        
        # 3. Actualizar roles de persona si se proporcionan
        # persona_update.rol_ids is not None: Esto permite enviar una lista vacía para quitar todos los roles.
        if persona_update.rol_ids is not None:
            roles_to_assign = db.query(DBRol).filter(DBRol.rol_id.in_(persona_update.rol_ids)).all()
            if len(roles_to_assign) != len(persona_update.rol_ids):
                found_role_ids = {r.rol_id for r in roles_to_assign}
                invalid_role_ids = set(persona_update.rol_ids) - found_role_ids
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Uno o más IDs de rol de persona no son válidos: {list(invalid_role_ids)}"
                )
            db_persona.roles = roles_to_assign # SQLAlchemy manejará la actualización de la tabla de unión

        db.commit()
        db.refresh(db_persona) # Refrescar para asegurar que las relaciones cargadas estén actualizadas
        return db_persona
    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Ocurrió un error inesperado al actualizar la Persona: {str(e)}")


@router.patch("/{persona_id}/activar", status_code=status.HTTP_204_NO_CONTENT)
def activate_persona(
    db_persona: DBPersona = Depends(get_persona_or_404),
    db: Session = Depends(get_db),
    current_user: auth_utils.Usuario = Depends(auth_utils.require_menu_access("/personas")) # Verificar acceso al menú de categorías
):
    """
    Activa el estado de una persona.
    """
    if db_persona.estado == EstadoEnum.activo:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="La persona ya está activa.")
    
    db_persona.estado = EstadoEnum.activo
    
    # 🔄 SINCRONIZACIÓN AUTOMÁTICA: Activar proveedores relacionados inactivos
    from ..models.proveedor import Proveedor as DBProveedor
    proveedores_relacionados = db.query(DBProveedor).filter(
        DBProveedor.persona_id == db_persona.persona_id,
        DBProveedor.estado == EstadoEnum.inactivo
    ).all()
    
    # Activar todos los proveedores inactivos relacionados con esta persona
    for proveedor in proveedores_relacionados:
        proveedor.estado = EstadoEnum.activo
        print(f"🔄 Sincronización: Activando proveedor ID {proveedor.proveedor_id} asociado a persona ID {db_persona.persona_id}")
    
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{persona_id}/desactivar", status_code=status.HTTP_204_NO_CONTENT)
def deactivate_persona(
    db_persona: DBPersona = Depends(get_persona_or_404),
    db: Session = Depends(get_db),
    current_user: auth_utils.Usuario = Depends(auth_utils.require_menu_access("/personas")) # Verificar acceso al menú de categorías
):
    """
    Desactiva el estado de una persona y su usuario asociado (si existe).
    Impide que un usuario se desactive a sí mismo.
    """
    if db_persona.estado == EstadoEnum.inactivo:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="La persona ya está inactiva.")

    # --- LÓGICA DE SEGURIDAD AÑADIDA ---
    # Comprobar si el usuario intenta desactivarse a sí mismo.
    if db_persona.usuario and db_persona.usuario.usuario_id == current_user.usuario_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No puedes desactivar tu propia cuenta de usuario."
        )
    # --- FIN DE LA LÓGICA DE SEGURIDAD ---

    db_persona.estado = EstadoEnum.inactivo
    
    # Si la persona tiene un usuario asociado, también lo desactivamos.
    if db_persona.usuario:
        db_persona.usuario.estado = EstadoEnum.inactivo
    
    # 🔄 SINCRONIZACIÓN AUTOMÁTICA: Desactivar proveedores relacionados
    from ..models.proveedor import Proveedor as DBProveedor
    proveedores_relacionados = db.query(DBProveedor).filter(
        DBProveedor.persona_id == db_persona.persona_id,
        DBProveedor.estado == EstadoEnum.activo
    ).all()
    
    # Desactivar todos los proveedores activos relacionados con esta persona
    for proveedor in proveedores_relacionados:
        proveedor.estado = EstadoEnum.inactivo
        print(f"🔄 Sincronización: Desactivando proveedor ID {proveedor.proveedor_id} asociado a persona ID {db_persona.persona_id}")
    
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def get_rol_or_404(
    rol_id: int = Path(..., title="El ID del rol"),
    db: Session = Depends(get_db)
) -> DBRol:
    """
    Dependencia para obtener un rol por su ID.
    Lanza un error 404 si no se encuentra.
    """
    rol = db.query(DBRol).filter(DBRol.rol_id == rol_id).first()
    if rol is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Rol no encontrado.")
    return rol

@router.post("/{persona_id}/roles/{rol_id}", response_model=PersonaWithRoles)
def assign_role_to_persona(
    persona: DBPersona = Depends(get_persona_or_404),
    rol: DBRol = Depends(get_rol_or_404),
    db: Session = Depends(get_db),
    current_user: auth_utils.Usuario = Depends(auth_utils.require_menu_access("/personas")) # Verificar acceso al menú de categorías
):
    """
    Asigna un rol específico a una persona.
    Retorna la persona con la lista actualizada de sus roles.
    """
    if rol in persona.roles:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"La persona ya tiene el rol '{rol.nombre_rol}'.")

    persona.roles.append(rol)
    db.add(persona)
    db.commit()
    db.refresh(persona)
    return persona

@router.delete("/{persona_id}/roles/{rol_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_role_from_persona(
    persona: DBPersona = Depends(get_persona_or_404),
    rol: DBRol = Depends(get_rol_or_404),
    db: Session = Depends(get_db),
    current_user: auth_utils.Usuario = Depends(auth_utils.require_menu_access("/personas")) # Verificar acceso al menú de categorías
):
    """
    Elimina un rol específico de una persona.
    """
    if rol not in persona.roles:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"La persona no tiene el rol '{rol.nombre_rol}'.")

    persona.roles.remove(rol)
    db.add(persona)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)