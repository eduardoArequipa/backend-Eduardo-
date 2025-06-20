# backEnd/app/routes/rol.py
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from sqlalchemy import or_ # Importar para búsqueda

from .. import auth as auth_utils
from ..database import get_db
from ..models.rol import Rol as DBRol # Importar el modelo SQLAlchemy
from ..models.enums import EstadoEnum
# Importar los esquemas Pydantic necesarios
from ..schemas.rol import Rol, RolCreate, RolUpdate

router = APIRouter(
    prefix="/roles",
    tags=["roles"]
)

ROLES_CAN_MANAGE_ROLES = ["Administrador"]

@router.post("/", response_model=Rol, status_code=status.HTTP_201_CREATED) # <-- CORREGIDO: Usamos el esquema Pydantic Rol
def create_rol(
    rol: RolCreate,
    db: Session = Depends(get_db),
    current_user: auth_utils.Usuario = Depends(auth_utils.get_current_active_user_with_role(ROLES_CAN_MANAGE_ROLES))
):
    """Crea un nuevo Rol."""
    db_rol = db.query(DBRol).filter(DBRol.nombre_rol == rol.nombre_rol).first()
    if db_rol:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Ya existe un rol con este nombre")

    new_rol = DBRol(**rol.model_dump())
    db.add(new_rol)
    db.commit()
    db.refresh(new_rol)
    return new_rol

@router.get("/", response_model=List[Rol]) # <-- CORREGIDO: Usamos una Lista del esquema Pydantic Rol
def read_roles(
    estado: Optional[EstadoEnum] = Query(None, description="Filtrar por estado"),
    search: Optional[str] = Query(None, description="Texto de búsqueda por nombre o descripción"),
    skip: int = Query(0, ge=0, description="Número de elementos a omitir (paginación)"),
    limit: int = Query(100, gt=0, description="Número máximo de elementos a retornar (paginación)"),
    db: Session = Depends(get_db),
    current_user: auth_utils.Usuario = Depends(auth_utils.get_current_active_user)
):
    """
    Obtiene una lista de Roles, con opciones de filtro, búsqueda y paginación.
    """
    query = db.query(DBRol)

    if estado:
        query = query.filter(DBRol.estado == estado)

    if search:
        query = query.filter(
            or_(
                DBRol.nombre_rol.ilike(f"%{search}%"),
                DBRol.descripcion.ilike(f"%{search}%")
            )
        )

    roles = query.offset(skip).limit(limit).all()

    return roles

@router.get("/{rol_id}", response_model=Rol) # <-- CORREGIDO: Usamos el esquema Pydantic Rol
def read_rol(
    rol_id: int,
    db: Session = Depends(get_db),
    current_user: auth_utils.Usuario = Depends(auth_utils.get_current_active_user)
):
    """Obtiene la información de un Rol específico por su ID."""
    rol = db.query(DBRol).filter(DBRol.rol_id == rol_id).first()
    if rol is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Rol no encontrado")
    return rol

@router.put("/{rol_id}", response_model=Rol) # <-- CORREGIDO: Usamos el esquema Pydantic Rol
def update_rol(
    rol_id: int,
    rol: RolUpdate,
    db: Session = Depends(get_db),
    current_user: auth_utils.Usuario = Depends(auth_utils.get_current_active_user_with_role(ROLES_CAN_MANAGE_ROLES))
):
    """Actualiza la información de un Rol existente por su ID."""
    db_rol = db.query(DBRol).filter(DBRol.rol_id == rol_id).first()
    if db_rol is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Rol no encontrado")

    if rol.nombre_rol is not None and rol.nombre_rol != db_rol.nombre_rol:
        existing_rol = db.query(DBRol).filter(DBRol.nombre_rol == rol.nombre_rol).first()
        if existing_rol:
             raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Ya existe un rol con este nombre")

    for field, value in rol.model_dump(exclude_unset=True).items():
        setattr(db_rol, field, value)

    db.commit()
    db.refresh(db_rol)
    return db_rol

@router.delete("/{rol_id}", status_code=status.HTTP_204_NO_CONTENT) # No model for 204
def delete_rol(
    rol_id: int,
    db: Session = Depends(get_db),
    current_user: auth_utils.Usuario = Depends(auth_utils.get_current_active_user_with_role(ROLES_CAN_MANAGE_ROLES))
):
    """
    Elimina (desactiva) un Rol por su ID.
    """
    db_rol = db.query(DBRol).filter(DBRol.rol_id == rol_id).first()
    if db_rol is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Rol no encontrado")

    db_rol.estado = EstadoEnum.inactivo
    db.commit()

    return {}