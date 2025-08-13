# backend/app/routes/marca.py

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from sqlalchemy import or_

from .. import auth as auth_utils
from ..database import get_db

from ..models.marca import Marca as DBMarca
from ..models.enums import EstadoEnum

from ..schemas.marca import (
    MarcaBase,
    MarcaCreate,
    Marca,
)

router = APIRouter(
    prefix="/marcas",
    tags=["marcas"]
)


@router.post("/", response_model=Marca, status_code=status.HTTP_201_CREATED)
def create_marca(
    marca: MarcaCreate,
    db: Session = Depends(get_db),
):
    """
    Crea una nueva marca en la base de datos.
    Requiere autenticación y roles específicos (Administrador, Empleado).
    """
    # Validar que el nombre de la marca sea único
    db_marca_existente = db.query(DBMarca).filter(DBMarca.nombre_marca == marca.nombre_marca).first()
    if db_marca_existente:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Ya existe una marca con este nombre.")

    # Crear la nueva marca con los datos del esquema
    new_marca = DBMarca(**marca.model_dump())

    db.add(new_marca)
    db.commit()
    db.refresh(new_marca) # Refrescar para obtener el marca_id y otros defaults de la DB

    return new_marca

@router.get("/", response_model=List[Marca])
def read_marcas(
    estado: Optional[EstadoEnum] = Query(None, description="Filtrar por estado"),
    search: Optional[str] = Query(None, description="Texto de búsqueda por nombre de marca"),
    skip: int = Query(0, ge=0, description="Número de elementos a omitir (paginación)"),
    limit: int = Query(100, gt=0, description="Número máximo de elementos a retornar (paginación)"),
    db: Session = Depends(get_db),
    current_user: auth_utils.Usuario = Depends(auth_utils.require_authenticated_user)
):
    """
    Obtiene una lista de Marcas con opciones de filtro, búsqueda y paginación.
    Accesible solo por usuarios con permisos de gestión de marcas.
    """
    query = db.query(DBMarca)

    if estado:
        query = query.filter(DBMarca.estado == estado)

    if search:
        query = query.filter(DBMarca.nombre_marca.ilike(f"%{search}%"))

    marcas = query.offset(skip).limit(limit).all()

    return marcas

@router.get("/{marca_id}", response_model=Marca)
def read_marca(
    marca_id: int,
    db: Session = Depends(get_db),
):
    """
    Obtiene una marca específica por su ID.
    Requiere autenticación y roles específicos.
    """
    marca = db.query(DBMarca).filter(DBMarca.marca_id == marca_id).first()

    if marca is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Marca no encontrada")

    return marca

@router.put("/{marca_id}", response_model=Marca)
def update_marca(
    marca_id: int,
    marca_update: MarcaCreate, 
    db: Session = Depends(get_db),
    current_user: auth_utils.Usuario = Depends(auth_utils.require_menu_access("/marcas")) # Verificar acceso al menú de categorías
):
    """
    Actualiza una marca existente por su ID.
    Requiere autenticación y roles específicos.
    """
    db_marca = db.query(DBMarca).filter(DBMarca.marca_id == marca_id).first()

    if db_marca is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Marca no encontrada.")

    update_data = marca_update.model_dump(exclude_unset=True)
    if 'nombre_marca' in update_data and update_data['nombre_marca'] != db_marca.nombre_marca:
        existing_marca_with_new_name = db.query(DBMarca).filter(DBMarca.nombre_marca == update_data['nombre_marca']).first()
        if existing_marca_with_new_name and existing_marca_with_new_name.marca_id != marca_id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Ya existe otra marca con este nombre.")

    for field, value in update_data.items():
        setattr(db_marca, field, value)


    db.commit()
    db.refresh(db_marca)

    return db_marca

# --- Endpoint para Eliminar/Desactivar una Marca por ID ---
@router.delete("/{marca_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_marca(
    marca_id: int,
    db: Session = Depends(get_db),
    current_user: auth_utils.Usuario = Depends(auth_utils.require_menu_access("/marcas")) # Verificar acceso al menú de categorías
):
    """
    Desactiva una marca por su ID (cambia su estado a 'inactivo').
    Requiere autenticación y roles específicos.
    """
    db_marca = db.query(DBMarca).filter(DBMarca.marca_id == marca_id).first()
    if db_marca is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Marca no encontrada.")

    if db_marca.estado == EstadoEnum.inactivo:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="La marca ya está inactiva.")

    db_marca.estado = EstadoEnum.inactivo

    db.commit()

    return {}

# --- ENDPOINT: Activar una Marca por ID ---
@router.patch("/{marca_id}", response_model=Marca)
def activate_marca(
    marca_id: int,
    db: Session = Depends(get_db),
):
    """
    Activa una marca por su ID (cambia su estado a 'activo').
    Requiere autenticación y roles específicos.
    """
    db_marca = db.query(DBMarca).filter(DBMarca.marca_id == marca_id).first()

    if db_marca is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Marca no encontrada.")

    if db_marca.estado == EstadoEnum.activo:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="La marca ya está activa.")

    db_marca.estado = EstadoEnum.activo

    db.commit()
    db.refresh(db_marca)

    return db_marca