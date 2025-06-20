# backend/app/routes/unidad_medida.py

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from sqlalchemy import or_

from .. import auth as auth_utils
from ..database import get_db

from ..models.unidad_medida import UnidadMedida as DBUnidadMedida
from ..models.enums import EstadoEnum

from ..schemas.unidad_medida import (
    UnidadMedidaBase,
    UnidadMedidaCreate,
    UnidadMedida,
)

# Define el router para las rutas de unidades de medida
router = APIRouter(
    prefix="/unidades-medida",
    tags=["unidades-medida"]
)

# Roles que tienen permiso para gestionar unidades de medida
ROLES_CAN_MANAGE_UNIDADES_MEDIDA = ["Administrador", "Empleado"]

# --- Endpoint para Crear una Nueva Unidad de Medida ---
@router.post("/", response_model=UnidadMedida, status_code=status.HTTP_201_CREATED)
def create_unidad_medida(
    unidad_medida: UnidadMedidaCreate,
    db: Session = Depends(get_db),
    current_user: auth_utils.Usuario = Depends(auth_utils.get_current_active_user_with_role(ROLES_CAN_MANAGE_UNIDADES_MEDIDA))
):
    """
    Crea una nueva unidad de medida en la base de datos.
    Requiere autenticación y roles específicos (Administrador, Empleado).
    """
    # Validar que el nombre de la unidad o la abreviatura sean únicos
    db_unidad_existente = db.query(DBUnidadMedida).filter(
        or_(
            DBUnidadMedida.nombre_unidad == unidad_medida.nombre_unidad,
            DBUnidadMedida.abreviatura == unidad_medida.abreviatura
        )
    ).first()
    if db_unidad_existente:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Ya existe una unidad de medida con este nombre o abreviatura.")

    # Crear la nueva unidad de medida con los datos del esquema
    new_unidad_medida = DBUnidadMedida(**unidad_medida.model_dump())
    new_unidad_medida.creado_por = current_user.usuario_id

    db.add(new_unidad_medida)
    db.commit()
    db.refresh(new_unidad_medida) # Refrescar para obtener el unidad_id y otros defaults de la DB

    return new_unidad_medida

# --- Endpoint para Listar Unidades de Medida ---
@router.get("/", response_model=List[UnidadMedida])
def read_unidades_medida(
    estado: Optional[EstadoEnum] = Query(None, description="Filtrar por estado"),
    search: Optional[str] = Query(None, description="Texto de búsqueda por nombre de unidad o abreviatura"),
    skip: int = Query(0, ge=0, description="Número de elementos a omitir (paginación)"),
    limit: int = Query(100, gt=0, description="Número máximo de elementos a retornar (paginación)"),
    db: Session = Depends(get_db),
    current_user: auth_utils.Usuario = Depends(auth_utils.get_current_active_user_with_role(ROLES_CAN_MANAGE_UNIDADES_MEDIDA))
):
    """
    Obtiene una lista de Unidades de Medida con opciones de filtro, búsqueda y paginación.
    Accesible solo por usuarios con permisos de gestión de unidades de medida.
    """
    query = db.query(DBUnidadMedida)

    if estado:
        query = query.filter(DBUnidadMedida.estado == estado)

    if search:
        query = query.filter(
            or_(
                DBUnidadMedida.nombre_unidad.ilike(f"%{search}%"),
                DBUnidadMedida.abreviatura.ilike(f"%{search}%"),
            )
        )

    unidades_medida = query.offset(skip).limit(limit).all()

    return unidades_medida

# --- Endpoint para Obtener una Unidad de Medida por ID ---
@router.get("/{unidad_id}", response_model=UnidadMedida)
def read_unidad_medida(
    unidad_id: int,
    db: Session = Depends(get_db),
    current_user: auth_utils.Usuario = Depends(auth_utils.get_current_active_user_with_role(ROLES_CAN_MANAGE_UNIDADES_MEDIDA))
):
    """
    Obtiene una unidad de medida específica por su ID.
    Requiere autenticación y roles específicos.
    """
    unidad_medida = db.query(DBUnidadMedida).filter(DBUnidadMedida.unidad_id == unidad_id).first()

    if unidad_medida is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unidad de medida no encontrada")

    return unidad_medida

# --- Endpoint para Actualizar una Unidad de Medida por ID ---
@router.put("/{unidad_id}", response_model=UnidadMedida)
def update_unidad_medida(
    unidad_id: int,
    unidad_medida_update: UnidadMedidaCreate, # Usamos UnidadMedidaCreate para los campos actualizables
    db: Session = Depends(get_db),
    current_user: auth_utils.Usuario = Depends(auth_utils.get_current_active_user_with_role(ROLES_CAN_MANAGE_UNIDADES_MEDIDA))
):
    """
    Actualiza una unidad de medida existente por su ID.
    Requiere autenticación y roles específicos.
    """
    db_unidad_medida = db.query(DBUnidadMedida).filter(DBUnidadMedida.unidad_id == unidad_id).first()

    if db_unidad_medida is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unidad de medida no encontrada.")

    update_data = unidad_medida_update.model_dump(exclude_unset=True)

    # Validar que el nombre de la unidad o la abreviatura sean únicos si se intentan actualizar
    if ('nombre_unidad' in update_data and update_data['nombre_unidad'] != db_unidad_medida.nombre_unidad) or \
       ('abreviatura' in update_data and update_data['abreviatura'] != db_unidad_medida.abreviatura):
        existing_unidad_with_new_data = db.query(DBUnidadMedida).filter(
            or_(
                DBUnidadMedida.nombre_unidad == update_data.get('nombre_unidad', db_unidad_medida.nombre_unidad),
                DBUnidadMedida.abreviatura == update_data.get('abreviatura', db_unidad_medida.abreviatura)
            )
        ).first()
        if existing_unidad_with_new_data and existing_unidad_with_new_data.unidad_id != unidad_id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Ya existe otra unidad de medida con este nombre o abreviatura.")

    for field, value in update_data.items():
        setattr(db_unidad_medida, field, value)

    db_unidad_medida.modificado_por = current_user.usuario_id

    db.commit()
    db.refresh(db_unidad_medida)

    return db_unidad_medida

# --- Endpoint para Eliminar/Desactivar una Unidad de Medida por ID ---
@router.delete("/{unidad_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_unidad_medida(
    unidad_id: int,
    db: Session = Depends(get_db),
    current_user: auth_utils.Usuario = Depends(auth_utils.get_current_active_user_with_role(ROLES_CAN_MANAGE_UNIDADES_MEDIDA))
):
    """
    Desactiva una unidad de medida por su ID (cambia su estado a 'inactivo').
    Requiere autenticación y roles específicos.
    """
    db_unidad_medida = db.query(DBUnidadMedida).filter(DBUnidadMedida.unidad_id == unidad_id).first()
    if db_unidad_medida is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unidad de medida no encontrada.")

    if db_unidad_medida.estado == EstadoEnum.inactivo:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="La unidad de medida ya está inactiva.")

    db_unidad_medida.estado = EstadoEnum.inactivo
    db_unidad_medida.modificado_por = current_user.usuario_id

    db.commit()

    return {}

# --- ENDPOINT: Activar una Unidad de Medida por ID ---
@router.patch("/{unidad_id}", response_model=UnidadMedida)
def activate_unidad_medida(
    unidad_id: int,
    db: Session = Depends(get_db),
    current_user: auth_utils.Usuario = Depends(auth_utils.get_current_active_user_with_role(ROLES_CAN_MANAGE_UNIDADES_MEDIDA))
):
    """
    Activa una unidad de medida por su ID (cambia su estado a 'activo').
    Requiere autenticación y roles específicos.
    """
    db_unidad_medida = db.query(DBUnidadMedida).filter(DBUnidadMedida.unidad_id == unidad_id).first()

    if db_unidad_medida is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unidad de medida no encontrada.")

    if db_unidad_medida.estado == EstadoEnum.activo:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="La unidad de medida ya está activa.")

    db_unidad_medida.estado = EstadoEnum.activo
    db_unidad_medida.modificado_por = current_user.usuario_id

    db.commit()
    db.refresh(db_unidad_medida)

    return db_unidad_medida