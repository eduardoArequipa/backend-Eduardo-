# backEnd/app/routes/categoria.py
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from sqlalchemy import or_

# Importa tus utilidades de auth y la dependencia get_db
from .. import auth as auth_utils # Importa el módulo auth con alias

from ..database import get_db

# Importa el modelo SQLAlchemy Categoria
from ..models.categoria import Categoria as DBCategoria # Usa el alias DBCategoria por convención

# Importa el Enum para el estado si lo necesitas en el router
from ..models.enums import EstadoEnum

# Importar tus esquemas Pydantic para Categoria
from ..schemas.categoria import (
    CategoriaBase,
    CategoriaCreate,
    CategoriaUpdate,
    Categoria,
    CategoriaNested
)

# *** CORREGIDO: NO necesitas importar el modelo de usuario directamente aquí ***
# para la anotación de tipo, ya que lo tienes accesible a través de auth_utils.
# La dependencia de FastAPI se encarga de inyectar el objeto correcto,
# y la anotación de tipo es solo para ayuda de herramientas como linters/editores.
# from ..models.usuario import Usuario as DBUsuario # <-- REMOVER/COMENTAR esta línea


router = APIRouter(
    prefix="/categorias",
    tags=["categorias"]
)

# Define qué roles pueden gestionar categorías (ej. solo Administrador)
ROLES_CAN_MANAGE_CATEGORIES = ["Administrador"]


# --- Endpoint para Crear una Nueva Categoría ---
@router.post("/", response_model=Categoria, status_code=status.HTTP_201_CREATED)
def create_categoria(
    categoria: CategoriaCreate,
    db: Session = Depends(get_db),
    # *** CORREGIDO: Usar auth_utils.Usuario como tipo para current_user ***
    current_user: auth_utils.Usuario = Depends(auth_utils.get_current_active_user_with_role(ROLES_CAN_MANAGE_CATEGORIES))
):
    """
    Crea una nueva Categoría.
    Solo accesible por usuarios con permisos de gestión de categorías.
    """
    db_categoria = db.query(DBCategoria).filter(DBCategoria.nombre_categoria == categoria.nombre_categoria).first()
    if db_categoria:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Ya existe una categoría con este nombre.")

    new_categoria = DBCategoria(**categoria.model_dump())

    # Si tu modelo DBCategoria tuviera campo creado_por (int), lo asignarías aquí:
    # new_categoria.creado_por = current_user.usuario_id

    db.add(new_categoria)
    db.commit()
    db.refresh(new_categoria)

    return new_categoria


# --- Endpoint para Listar Categorías ---
@router.get("/", response_model=List[Categoria])
def read_categorias(
    estado: Optional[EstadoEnum] = Query(None, description="Filtrar por estado"),
    search: Optional[str] = Query(None, description="Texto de búsqueda por nombre"),
    skip: int = Query(0, ge=0, description="Número de elementos a omitir (paginación)"),
    limit: int = Query(100, gt=0, description="Número máximo de elementos a retornar (paginación)"),
    db: Session = Depends(get_db),
    # *** CORREGIDO: Usar auth_utils.Usuario como tipo para current_user ***
    current_user: auth_utils.Usuario = Depends(auth_utils.get_current_active_user_with_role(ROLES_CAN_MANAGE_CATEGORIES)) # Restringido por defecto
):
    """
    Obtiene una lista de Categorías con opciones de filtro, búsqueda y paginación.
    Accesible solo por usuarios con permisos de gestión de categorías (por defecto).
    """
    query = db.query(DBCategoria)

    if estado:
        query = query.filter(DBCategoria.estado == estado)

    if search:
        query = query.filter(DBCategoria.nombre_categoria.ilike(f"%{search}%"))

    categorias = query.offset(skip).limit(limit).all()

    return categorias


# --- Endpoint para Obtener una Categoría por ID ---
@router.get("/{categoria_id}", response_model=Categoria)
def read_categoria(
    categoria_id: int,
    db: Session = Depends(get_db),
    current_user: auth_utils.Usuario = Depends(auth_utils.get_current_active_user_with_role(ROLES_CAN_MANAGE_CATEGORIES)) # Restringido por defecto
):
    """
    Obtiene la información de una Categoría específica por su ID.
    Accesible solo por usuarios con permisos de gestión de categorías (por defecto).
    """
    categoria = db.query(DBCategoria).filter(DBCategoria.categoria_id == categoria_id).first()

    if categoria is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Categoría no encontrada")

    return categoria


# --- Endpoint para Actualizar una Categoría por ID ---
@router.put("/{categoria_id}", response_model=Categoria)
def update_categoria(
    categoria_id: int,
    categoria_update: CategoriaUpdate,
    db: Session = Depends(get_db),
    # *** CORREGIDO: Usar auth_utils.Usuario como tipo para current_user ***
    current_user: auth_utils.Usuario = Depends(auth_utils.get_current_active_user_with_role(ROLES_CAN_MANAGE_CATEGORIES))
):
    """
    Actualiza la información de una Categoría existente por su ID.
    Solo accesible por usuarios con permisos de gestión de categorías.
    """
    db_categoria = db.query(DBCategoria).filter(DBCategoria.categoria_id == categoria_id).first()
    if db_categoria is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Categoría no encontrada.")

    if categoria_update.nombre_categoria is not None and categoria_update.nombre_categoria != db_categoria.nombre_categoria:
         existing_categoria_with_new_name = db.query(DBCategoria).filter(DBCategoria.nombre_categoria == categoria_update.nombre_categoria).first()
         if existing_categoria_with_new_name and existing_categoria_with_new_name.categoria_id != categoria_id:
              raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Ya existe otra categoría con este nombre.")

    update_data = categoria_update.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(db_categoria, field, value)

    # Si tu modelo DBCategoria tuviera campo modificado_por (int), lo asignarías aquí:
    # db_categoria.modificado_por = current_user.usuario_id

    db.commit()
    db.refresh(db_categoria)

    return db_categoria


# --- Endpoint para Eliminar/Desactivar una Categoría por ID (Soft Delete) ---
@router.delete("/{categoria_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_categoria(
    categoria_id: int,
    db: Session = Depends(get_db),
    # *** CORREGIDO: Usar auth_utils.Usuario como tipo para current_user ***
    current_user: auth_utils.Usuario = Depends(auth_utils.get_current_active_user_with_role(ROLES_CAN_MANAGE_CATEGORIES))
):
    """
    Desactiva (cambia el estado a inactivo) una Categoría por su ID.
    Solo accesible por usuarios con permisos de gestión de categorías.
    """
    db_categoria = db.query(DBCategoria).filter(DBCategoria.categoria_id == categoria_id).first()
    if db_categoria is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Categoría no encontrada.")

    if db_categoria.estado == EstadoEnum.inactivo:
         raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="La categoría ya está inactiva.")

    db_categoria.estado = EstadoEnum.inactivo

 
    db.commit()

    return {}

@router.patch("/{categoria_id}/activar", response_model=Categoria)
def activate_categoria(
    categoria_id: int,
    db: Session = Depends(get_db),
    # *** CORREGIDO: Usar auth_utils.Usuario como tipo para current_user ***
    current_user: auth_utils.Usuario = Depends(auth_utils.get_current_active_user_with_role(ROLES_CAN_MANAGE_CATEGORIES))
):
    """
    Activa (cambia el estado a activo) una Categoría por su ID.
    Solo accesible por usuarios con permisos de gestión de categorías.
    """
    db_categoria = db.query(DBCategoria).filter(DBCategoria.categoria_id == categoria_id).first()
    if db_categoria is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Categoría no encontrada.")

    if db_categoria.estado == EstadoEnum.activo:
         raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="La categoría ya está activa.")

    db_categoria.estado = EstadoEnum.activo

    # Si tu modelo DBCategoria tuviera campo modificado_por (int), lo asignarías aquí:
    # db_categoria.modificado_por = current_user.usuario_id

    db.commit()
    db.refresh(db_categoria)
    return db_categoria
