from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query, Path, Response
from sqlalchemy.orm import Session
from sqlalchemy import or_
from sqlalchemy import func

from .. import auth as auth_utils 

from ..database import get_db
from ..models.categoria import Categoria as DBCategoria
from ..models.enums import EstadoEnum
from ..schemas.categoria import (
    CategoriaCreate,
    CategoriaUpdate,
    Categoria,
    CategoriaPagination # Importar el nuevo esquema de paginación
)

router = APIRouter(
    prefix="/categorias",
    tags=["categorias"]
)
ROLES_CAN_MANAGE_CATEGORIES = ["Administrador"]

def get_categoria_or_404(
    categoria_id: int = Path(..., title="El ID de la categoría"),
    db: Session = Depends(get_db)
) -> DBCategoria:
    """
    Dependencia para obtener una categoría por su ID.
    Lanza un error 404 si no se encuentra.
    """
    categoria = db.query(DBCategoria).filter(DBCategoria.categoria_id == categoria_id).first()
    if categoria is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Categoría no encontrada.")
    return categoria

@router.post("/", response_model=Categoria, status_code=status.HTTP_201_CREATED)
def create_categoria(
    categoria: CategoriaCreate,
    db: Session = Depends(get_db),
    current_user: auth_utils.Usuario = Depends(auth_utils.require_menu_access("/categorias")) # Verificar acceso al menú de categorías
):
    """
    Crea una nueva Categoría.
    Solo accesible por usuarios con permisos de gestión de categorías.
    """
    db_categoria = db.query(DBCategoria).filter(func.strip(func.lower(DBCategoria.nombre_categoria)) == categoria.nombre_categoria.lower().strip()
).first()
    if db_categoria:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Ya existe una categoría con este nombre.")

    new_categoria = DBCategoria(**categoria.model_dump())

    db.add(new_categoria)
    db.commit()
    db.refresh(new_categoria)

    return new_categoria

@router.get("/", response_model=CategoriaPagination) # Cambiado a CategoriaPagination
def read_categorias(
    estado: Optional[EstadoEnum] = Query(None, description="Filtrar por estado"),
    search: Optional[str] = Query(None, description="Texto de búsqueda por nombre"),
    skip: int = Query(0, ge=0, description="Número de elementos a omitir (paginación)"),
    limit: int = Query(100, gt=0, description="Número máximo de elementos a retornar (paginación)"),
    db: Session = Depends(get_db),
    current_user: auth_utils.Usuario = Depends(auth_utils.require_authenticated_user)
):
    """
    Obtiene una lista de Categorías con opciones de filtro, búsqueda y paginación.
    Accesible por cualquier usuario autenticado (para uso en filtros).
    """
    query = db.query(DBCategoria)

    if estado:
        query = query.filter(DBCategoria.estado == estado)

    if search:
        query = query.filter(DBCategoria.nombre_categoria.ilike(f"%{search}%"))

    total = query.count() # Contar el total de categorías antes de aplicar skip/limit
    categorias = query.offset(skip).limit(limit).all()

    return {"items": categorias, "total": total} # Devolver el objeto de paginación

@router.get("/{categoria_id}", response_model=Categoria)
def read_categoria(
    categoria: DBCategoria = Depends(get_categoria_or_404),
    current_user: auth_utils.Usuario = Depends(auth_utils.require_menu_access("/categorias")) # Verificar acceso al menú de categorías
):
    """
    Obtiene la información de una Categoría específica por su ID.
    Accesible solo por usuarios con permisos de gestión de categorías.
    """
    return categoria

@router.put("/{categoria_id}", response_model=Categoria)
def update_categoria(
    categoria_update: CategoriaUpdate,
    db_categoria: DBCategoria = Depends(get_categoria_or_404),
    db: Session = Depends(get_db),
    current_user: auth_utils.Usuario = Depends(auth_utils.require_menu_access("/categorias")) # Verificar acceso al menú de categorías
):
    """
    Actualiza la información de una Categoría existente por su ID.
    Solo accesible por usuarios con permisos de gestión de categorías.
    """
    if categoria_update.nombre_categoria is not None and categoria_update.nombre_categoria != db_categoria.nombre_categoria:
         existing_categoria_with_new_name = db.query(DBCategoria).filter(DBCategoria.nombre_categoria == categoria_update.nombre_categoria).first()
         if existing_categoria_with_new_name and existing_categoria_with_new_name.categoria_id != db_categoria.categoria_id:
              raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Ya existe otra categoría con este nombre.")

    update_data = categoria_update.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(db_categoria, field, value)
    db.commit()
    db.refresh(db_categoria)

    return db_categoria

@router.delete("/{categoria_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_categoria(
    db_categoria: DBCategoria = Depends(get_categoria_or_404),
    db: Session = Depends(get_db),
    current_user: auth_utils.Usuario = Depends(auth_utils.require_menu_access("/categorias")) # Verificar acceso al menú de categorías
):
    """
    Desactiva (cambia el estado a inactivo) una Categoría por su ID.
    Solo accesible por usuarios con permisos de gestión de categorías.
    """
    if db_categoria.estado == EstadoEnum.inactivo:
         raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="La categoría ya está inactiva.")

    db_categoria.estado = EstadoEnum.inactivo
 
    db.commit()

    return Response(status_code=status.HTTP_204_NO_CONTENT)

@router.patch("/{categoria_id}/activar", response_model=Categoria)
def activate_categoria(
    db_categoria: DBCategoria = Depends(get_categoria_or_404),
    db: Session = Depends(get_db),
    current_user: auth_utils.Usuario = Depends(auth_utils.require_menu_access("/categorias")) # Verificar acceso al menú de categorías
):
    """
    Activa (cambia el estado a activo) una Categoría por su ID.
    Solo accesible por usuarios con permisos de gestión de categorías.
    """
    if db_categoria.estado == EstadoEnum.activo:
         raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="La categoría ya está activa.")

    db_categoria.estado = EstadoEnum.activo

    db.commit()
    db.refresh(db_categoria)
    return db_categoria