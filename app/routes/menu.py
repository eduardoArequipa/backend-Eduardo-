# backEnd/app/routes/menu.py
from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from .. import auth as auth_utils
from ..database import get_db
from ..models.menu import Menu as DBMenu
from ..schemas.menu import MenuInDB

router = APIRouter(
    prefix="/menus",
    tags=["menus"]
)

@router.get("/", response_model=List[MenuInDB])
def read_menus(
    db: Session = Depends(get_db),
    current_user: auth_utils.Usuario = Depends(auth_utils.get_current_active_user)
):
    """
    Obtiene todos los menús/módulos disponibles en el sistema.
    """
    menus = db.query(DBMenu).order_by(DBMenu.menu_id).all()
    print(f"[DEBUG BACKEND] Enviando {len(menus)} menús: {[menu.nombre for menu in menus]}")
    return menus

@router.get("/{menu_id}", response_model=MenuInDB)
def read_menu(
    menu_id: int,
    db: Session = Depends(get_db),
    current_user: auth_utils.Usuario = Depends(auth_utils.get_current_active_user)
):
    """
    Obtiene un menú específico por su ID.
    """
    menu = db.query(DBMenu).filter(DBMenu.menu_id == menu_id).first()
    if not menu:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Menú no encontrado.")
    return menu