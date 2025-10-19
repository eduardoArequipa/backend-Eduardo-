# backend/app/routes/marca.py

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from sqlalchemy import or_, func

from .. import auth as auth_utils
from ..database import get_db

from ..models.marca import Marca as DBMarca
from ..models.enums import EstadoEnum

from ..schemas.marca import (
    MarcaBase,
    MarcaCreate,
    Marca,
    MarcaPagination,
)

router = APIRouter(
    prefix="/marcas",
    tags=["marcas"]
)


@router.post("/", response_model=Marca, status_code=status.HTTP_201_CREATED)
def create_marca(
    marca: MarcaCreate,
    db: Session = Depends(get_db),
    current_user: auth_utils.Usuario = Depends(auth_utils.require_menu_access("/marcas"))
):
    """
    Crea una nueva marca en la base de datos.
    Requiere autenticación y roles específicos (Administrador, Empleado).
    """
    # Validar que el nombre de la marca sea único (ignorando mayúsculas/minúsculas y espacios)
    nombre_limpio = marca.nombre_marca.strip()
    db_marca_existente = db.query(DBMarca).filter(func.lower(DBMarca.nombre_marca) == func.lower(nombre_limpio)).first()
    if db_marca_existente:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Ya existe una marca con este nombre.")

    # Crear la nueva marca con los datos del esquema y el nombre limpio
    new_marca_data = marca.model_dump()
    new_marca_data['nombre_marca'] = nombre_limpio
    new_marca = DBMarca(**new_marca_data)

    db.add(new_marca)
    db.commit()
    db.refresh(new_marca) # Refrescar para obtener el marca_id y otros defaults de la DB

    return new_marca

@router.get("/", response_model=MarcaPagination)
def read_marcas(
    estado: Optional[EstadoEnum] = Query(None, description="Filtrar por estado"),
    search: Optional[str] = Query(None, description="Texto de búsqueda por nombre de marca"),
    skip: int = Query(0, ge=0, description="Número de elementos a omitir (paginación)"),
    limit: int = Query(10, gt=0, le=100, description="Número máximo de elementos a retornar (paginación)"),
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

    # Obtener el total de registros (antes de aplicar paginación)
    total = query.count()

    # Aplicar paginación y ordenar por fecha de creación descendente
    marcas = query.order_by(DBMarca.creado_en.desc()).offset(skip).limit(limit).all()

    return {
        "items": marcas,
        "total": total
    }

@router.get("/{marca_id}", response_model=Marca)
def read_marca(
    marca_id: int,
    db: Session = Depends(get_db),
    current_user: auth_utils.Usuario = Depends(auth_utils.require_authenticated_user)
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

    # Si se está actualizando el nombre, validar duplicados (ignorando mayúsculas/minúsculas y espacios)
    if "nombre_marca" in update_data:
        nombre_limpio = update_data["nombre_marca"].strip()
        
        # Comprobar si el nombre limpio es diferente al existente (ignorando mayúsculas/minúsculas)
        if nombre_limpio.lower() != db_marca.nombre_marca.lower():
            # Buscar si ya existe otra marca con ese nombre
            existing_marca = db.query(DBMarca).filter(
                func.lower(DBMarca.nombre_marca) == func.lower(nombre_limpio),
                DBMarca.marca_id != marca_id
            ).first()
            
            if existing_marca:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Ya existe otra marca con este nombre.")
        
        # Usar el nombre limpio para la actualización
        update_data["nombre_marca"] = nombre_limpio

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
    current_user: auth_utils.Usuario = Depends(auth_utils.require_menu_access("/marcas"))
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