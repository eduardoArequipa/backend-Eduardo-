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
from ..models.enums import EstadoEnum
from ..schemas.rol import RolInDB
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
    
    response_data = {
        "rol_id": rol.rol_id,
        "nombre_rol": rol.nombre_rol,
        "descripcion": rol.descripcion,
        "estado": rol.estado.value, # Asegurarse de que el Enum se serialice como string
        "menus": [MenuInDB.model_validate(menu) for menu in rol.menus] # <--- ¡CAMBIO AQUÍ! No .model_dump()
    }
    print(f"[DEBUG BACKEND] Enviando respuesta para GET /roles/{rol_id}: {response_data}")
    return RolInDB.model_validate(response_data) # <--- ¡CAMBIO AQUÍ! Forzar validación final

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
