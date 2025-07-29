# backEnd/app/routes/rol.py

from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query, Path, Response
from sqlalchemy.orm import Session
from sqlalchemy import or_

from .. import auth as auth_utils
from ..database import get_db
from ..models.rol import Rol as DBRol
from ..models.enums import EstadoEnum
# Importamos los esquemas actualizados
from ..schemas.rol import RolInDB, RolCreate, RolUpdate # <-- ¡CAMBIO AQUÍ! (Rol renombrado a RolInDB)

router = APIRouter(
    prefix="/roles",
    tags=["roles"]
)

# Roles de USUARIO que tienen permiso para gestionar otros roles
ROLES_CAN_MANAGE_ROLES = ["Administrador"]

# --- Dependencias Reutilizables ---
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

# --- Rutas de API para Roles ---

@router.post("/", response_model=RolInDB, status_code=status.HTTP_201_CREATED) # <-- ¡CAMBIO AQUÍ! (response_model)
def create_rol(
    rol_create: RolCreate, # Renombrado para claridad
    db: Session = Depends(get_db),
    current_user: auth_utils.Usuario = Depends(auth_utils.get_current_active_user_with_role(ROLES_CAN_MANAGE_ROLES))
):
    """
    Crea un nuevo Rol.
    Solo accesible para usuarios con roles de gestión de roles (Administrador).
    """
    db.begin_nested() # Inicia una transacción anidada
    try:
        if db.query(DBRol).filter(DBRol.nombre_rol == rol_create.nombre_rol).first():
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"Ya existe un rol con el nombre '{rol_create.nombre_rol}'.") # <-- ¡CAMBIO AQUÍ! (409 Conflict)

        new_rol = DBRol(**rol_create.model_dump())
        db.add(new_rol)
        db.commit() # Confirma la creación del rol
        db.refresh(new_rol) # Refresca el objeto para asegurar que el ID y otros datos se carguen
        return new_rol
    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Ocurrió un error inesperado al crear el Rol: {str(e)}")


@router.get("/", response_model=List[RolInDB]) # <-- ¡CAMBIO AQUÍ! (response_model)
def read_roles(
    estado: Optional[EstadoEnum] = Query(None, description="Filtrar por estado del rol"),
    search: Optional[str] = Query(None, description="Texto de búsqueda por nombre o descripción del rol"),
    skip: int = Query(0, ge=0), limit: int = Query(100, gt=0),
    db: Session = Depends(get_db),
    current_user: auth_utils.Usuario = Depends(auth_utils.get_current_active_user) # Todos los usuarios autenticados pueden leer roles
):
    """
    Obtiene una lista de Roles, con opciones de filtro, búsqueda y paginación.
    """
    query = db.query(DBRol)
    if estado:
        query = query.filter(DBRol.estado == estado)
    if search:
        search_pattern = f"%{search}%"
        query = query.filter(or_(
            DBRol.nombre_rol.ilike(search_pattern),
            DBRol.descripcion.ilike(search_pattern)
        ))
    return query.order_by(DBRol.rol_id.desc()).offset(skip).limit(limit).all()

@router.get("/{rol_id}", response_model=RolInDB) # <-- ¡CAMBIO AQUÍ! (response_model)
def read_rol(
    rol: DBRol = Depends(get_rol_or_404),
    current_user: auth_utils.Usuario = Depends(auth_utils.get_current_active_user)
):
    """Obtiene la información de un Rol específico por su ID."""
    return rol

@router.put("/{rol_id}", response_model=RolInDB) # <-- ¡CAMBIO AQUÍ! (response_model)
def update_rol(
    rol_update: RolUpdate,
    db_rol: DBRol = Depends(get_rol_or_404),
    db: Session = Depends(get_db),
    current_user: auth_utils.Usuario = Depends(auth_utils.get_current_active_user_with_role(ROLES_CAN_MANAGE_ROLES))
):
    """
    Actualiza la información de un Rol existente por su ID.
    Solo accesible para usuarios con roles de gestión de roles (Administrador).
    """
    db.begin_nested() # Inicia una transacción anidada
    try:
        # Validar unicidad del nombre del rol si ha cambiado
        if rol_update.nombre_rol and rol_update.nombre_rol != db_rol.nombre_rol:
            if db.query(DBRol).filter(DBRol.nombre_rol == rol_update.nombre_rol).first():
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"Ya existe un rol con el nombre '{rol_update.nombre_rol}'.") # <-- ¡CAMBIO AQUÍ! (409 Conflict)

        update_data = rol_update.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(db_rol, field, value)

        db.commit()
        db.refresh(db_rol)
        return db_rol
    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Ocurrió un error inesperado al actualizar el Rol: {str(e)}")


@router.delete("/{rol_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_rol(
    db_rol: DBRol = Depends(get_rol_or_404),
    db: Session = Depends(get_db),
    current_user: auth_utils.Usuario = Depends(auth_utils.get_current_active_user_with_role(ROLES_CAN_MANAGE_ROLES))
):
    """
    Elimina (desactiva lógicamente) un Rol por su ID.
    Solo accesible para usuarios con roles de gestión de roles (Administrador).
    """
    if db_rol.estado == EstadoEnum.inactivo:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="El rol ya está inactivo.")
    
    db_rol.estado = EstadoEnum.inactivo
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)

# No hay una ruta para "activar" explícitamente porque la lógica de `update_rol`
# ya permite cambiar el estado de `inactivo` a `activo` si se envía `estado: "activo"`
# en la actualización. Si se necesita un endpoint separado, se puede añadir.