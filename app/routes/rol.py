# backEnd/app/routes/rol.py

from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query, Path, Response
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import or_

from .. import auth as auth_utils
from ..database import get_db
from ..models.rol import Rol as DBRol
from ..models.menu import Menu as DBMenu
from ..models.rol_menu import RolMenu as DBRolMenu
from ..models.persona_rol import PersonaRol as DBPersonaRol
from ..models.enums import EstadoEnum
from ..schemas.rol import RolInDB, RolCreate, RolUpdate
from ..schemas.menu import MenuInDB, RolMenuUpdate

router = APIRouter(
    prefix="/roles",
    tags=["roles"]
)


@router.get("/", response_model=List[RolInDB])
def read_roles(
    db: Session = Depends(get_db),
    current_user: auth_utils.Usuario = Depends(auth_utils.require_authenticated_user)
):
    return db.query(DBRol).options(joinedload(DBRol.menus)).order_by(DBRol.rol_id).all()

@router.get("/{rol_id}", response_model=RolInDB)
def read_rol(
    rol_id: int,
    db: Session = Depends(get_db),
    current_user: auth_utils.Usuario = Depends(auth_utils.require_menu_access("/roles")) # Verificar acceso al menú de categorías
):
    rol = db.query(DBRol).options(joinedload(DBRol.menus)).filter(DBRol.rol_id == rol_id).first()
    if not rol:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Rol no encontrado.")
    
    return rol

@router.put("/{rol_id}/menus", status_code=status.HTTP_204_NO_CONTENT)
def update_menus_for_role(
    rol_menu_update: RolMenuUpdate,
    rol_id: int = Path(..., title="El ID del rol a actualizar"),
    db: Session = Depends(get_db),
    current_user: auth_utils.Usuario = Depends(auth_utils.require_menu_access("/roles")) # Verificar acceso al menú de categorías
):
    rol = db.query(DBRol).filter(DBRol.rol_id == rol_id).first()
    if not rol:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Rol no encontrado.")

    menu_ids = set(rol_menu_update.menu_ids)
    rol.menus = db.query(DBMenu).filter(DBMenu.menu_id.in_(menu_ids)).all()

    try:
        db.commit()
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Error al guardar: {str(e)}")


@router.post("/", response_model=RolInDB, status_code=status.HTTP_201_CREATED)
def create_rol(
    rol_data: RolCreate,
    db: Session = Depends(get_db),
    current_user: auth_utils.Usuario = Depends(auth_utils.require_menu_access("/roles"))
):
    """
    Crea un nuevo rol con validación de duplicados (case-insensitive).
    """
    # Verificar si ya existe un rol con el mismo nombre (case-insensitive)
    existing_rol = db.query(DBRol).filter(
        DBRol.nombre_rol.ilike(rol_data.nombre_rol.strip())
    ).first()
    
    if existing_rol:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, 
            detail=f"Ya existe un rol con el nombre '{rol_data.nombre_rol}'"
        )
    
    try:
        db_rol = DBRol(**rol_data.model_dump())
        db.add(db_rol)
        db.commit()
        db.refresh(db_rol)
        return db_rol
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
            detail="Error al crear el rol."
        )


@router.put("/{rol_id}", response_model=RolInDB)
def update_rol(
    rol_id: int,
    rol_data: RolUpdate,
    db: Session = Depends(get_db),
    current_user: auth_utils.Usuario = Depends(auth_utils.require_menu_access("/roles"))
):
    """
    Actualiza un rol existente con validación de duplicados (case-insensitive).
    """
    db_rol = db.query(DBRol).filter(DBRol.rol_id == rol_id).first()
    if not db_rol:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Rol no encontrado.")
    
    # Si se está actualizando el nombre, verificar duplicados
    if rol_data.nombre_rol and rol_data.nombre_rol.strip() != db_rol.nombre_rol:
        existing_rol = db.query(DBRol).filter(
            DBRol.nombre_rol.ilike(rol_data.nombre_rol.strip()),
            DBRol.rol_id != rol_id
        ).first()
        
        if existing_rol:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Ya existe otro rol con el nombre '{rol_data.nombre_rol}'"
            )
    
    # ✅ VALIDACIÓN AÑADIDA: No permitir desactivar roles asignados
    update_data = rol_data.model_dump(exclude_unset=True)
    
    # Si se está intentando desactivar el rol, verificar que no esté asignado
    if 'estado' in update_data and update_data['estado'] == EstadoEnum.inactivo and db_rol.estado == EstadoEnum.activo:
        personas_con_rol = db.query(DBPersonaRol).filter(DBPersonaRol.rol_id == rol_id).count()
        if personas_con_rol > 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"No se puede desactivar el rol '{db_rol.nombre_rol}' porque está asignado a {personas_con_rol} persona(s). Primero remueve el rol de todas las personas."
            )
    
    try:
        # Actualizar campos proporcionados
        for key, value in update_data.items():
            setattr(db_rol, key, value)
        
        db.commit()
        db.refresh(db_rol)
        return db_rol
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error al actualizar el rol."
        )


@router.delete("/{rol_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_rol(
    rol_id: int,
    db: Session = Depends(get_db),
    current_user: auth_utils.Usuario = Depends(auth_utils.require_menu_access("/roles"))
):
    """
    Elimina un rol si no está asignado a ninguna persona.
    """
    db_rol = db.query(DBRol).filter(DBRol.rol_id == rol_id).first()
    if not db_rol:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Rol no encontrado.")
    
    # Verificar si el rol está asignado a alguna persona
    personas_con_rol = db.query(DBPersonaRol).filter(DBPersonaRol.rol_id == rol_id).count()
    if personas_con_rol > 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"No se puede eliminar el rol '{db_rol.nombre_rol}' porque está asignado a {personas_con_rol} persona(s)."
        )
    
    try:
        db.delete(db_rol)
        db.commit()
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error al eliminar el rol."
        )
