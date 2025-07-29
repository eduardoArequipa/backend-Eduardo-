from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from sqlalchemy import or_
from .. import auth as auth_utils #
from ..database import get_db
from ..models.empresa import Empresa as DBEmpresa # Usa el alias DBEmpresa
from ..models.enums import EstadoEnum

from ..schemas.empresa import (
    Empresa,
    EmpresaCreate, 
    EmpresaUpdate,
    EmpresaNested 
)
router = APIRouter(
    prefix="/empresas", 
    tags=["empresas"] 
)

ROLES_CAN_MANAGE_EMPRESAS = ["Administrador", "Empleado"]


@router.post("/", response_model=Empresa, status_code=status.HTTP_201_CREATED)
def create_empresa(
    empresa: EmpresaCreate, # Espera tu esquema EmpresaCreate
    db: Session = Depends(get_db),
    current_user: auth_utils.Usuario = Depends(auth_utils.get_current_active_user_with_role(ROLES_CAN_MANAGE_EMPRESAS))
):
    """
    Crea una nueva Empresa.
    Solo accesible por usuarios con permisos de gestión de empresas.
    """
    if empresa.identificacion:
        db_empresa_identificacion = db.query(DBEmpresa).filter(DBEmpresa.identificacion == empresa.identificacion).first()
        if db_empresa_identificacion:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Ya existe una empresa con esta Identificación: {empresa.identificacion}")

    new_empresa = DBEmpresa(**empresa.model_dump())

    db.add(new_empresa) 
    db.commit() 
    db.refresh(new_empresa) 

    return new_empresa

@router.get("/", response_model=List[Empresa]) 
def read_empresas(
    estado: Optional[EstadoEnum] = Query(None, description="Filtrar por estado"),
    search: Optional[str] = Query(None, description="Texto de búsqueda por razón social o identificación"), # Búsqueda combinada
    skip: int = Query(0, ge=0, description="Número de elementos a omitir (paginación)"),
    limit: int = Query(100, gt=0, description="Número máximo de elementos a retornar (paginación)"),
    without_proveedor: Optional[bool] = Query(None, description="Filtrar empresas que no tienen un proveedor asociado"),
    db: Session = Depends(get_db),
    current_user: auth_utils.Usuario = Depends(auth_utils.get_current_active_user_with_role(ROLES_CAN_MANAGE_EMPRESAS))
):
    """
    Obtiene una lista de Empresas con opciones de filtro, búsqueda y paginación.
    Opcionalmente, filtra empresas que no tienen un proveedor asociado.
    Accesible solo por usuarios con permisos de gestión de empresas (por defecto).
    """
    query = db.query(DBEmpresa)

    # Aplicar filtros
    if estado:
        query = query.filter(DBEmpresa.estado == estado)

    if search:
        query = query.filter(
            or_(
                DBEmpresa.razon_social.ilike(f"%{search}%"),
                DBEmpresa.identificacion.ilike(f"%{search}%"),
            )
        )

    if without_proveedor is True:
        query = query.filter(DBEmpresa.proveedor.is_(None)) # Filtra donde la relación proveedor es NULL
    elif without_proveedor is False:
         query = query.filter(DBEmpresa.proveedor.isnot(None))

    empresas = query.offset(skip).limit(limit).all()

    return empresas


@router.get("/{empresa_id}", response_model=Empresa)
def read_empresa(
    empresa_id: int,
    db: Session = Depends(get_db),
    current_user: auth_utils.Usuario = Depends(auth_utils.get_current_active_user_with_role(ROLES_CAN_MANAGE_EMPRESAS))
):
    """
    Obtiene la información de una Empresa específica por su ID.
    Accesible solo por usuarios con permisos de gestión de empresas (por defecto).
    """
    empresa = db.query(DBEmpresa).filter(DBEmpresa.empresa_id == empresa_id).first()

    if empresa is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Empresa no encontrada")

    return empresa # Retorna el objeto DBEmpresa que FastAPI serializa a Empresa

@router.put("/{empresa_id}", response_model=Empresa) # Retorna el esquema Empresa
def update_empresa(
    empresa_id: int,
    empresa_update: EmpresaUpdate, # Espera tu esquema EmpresaUpdate (campos opcionales)
    db: Session = Depends(get_db),
    current_user: auth_utils.Usuario = Depends(auth_utils.get_current_active_user_with_role(ROLES_CAN_MANAGE_EMPRESAS))
):
    """
    Actualiza la información de una Empresa existente por su ID.
    Permite actualizar varios campos.
    Solo accesible por usuarios con permisos de gestión de empresas.
    """
    # 1. Obtener la empresa por ID
    db_empresa = db.query(DBEmpresa).filter(DBEmpresa.empresa_id == empresa_id).first()

    if db_empresa is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Empresa no encontrada.")

    if empresa_update.identificacion is not None and empresa_update.identificacion != db_empresa.identificacion:
         existing_empresa_with_new_identificacion = db.query(DBEmpresa).filter(DBEmpresa.identificacion == empresa_update.identificacion).first()
         if existing_empresa_with_new_identificacion and existing_empresa_with_new_identificacion.empresa_id != empresa_id:
              raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Ya existe otra empresa con esta Identificación: {empresa_update.identificacion}")

    update_data = empresa_update.model_dump(exclude_unset=True)

    for field, value in update_data.items():
        setattr(db_empresa, field, value)

    db.commit() # Confirmar la transacción
    db.refresh(db_empresa) 

    return db_empresa


@router.delete("/{empresa_id}", status_code=status.HTTP_204_NO_CONTENT) # 204 No Content en éxito sin cuerpo
def delete_empresa(
    empresa_id: int,
    db: Session = Depends(get_db),
    current_user: auth_utils.Usuario = Depends(auth_utils.get_current_active_user_with_role(ROLES_CAN_MANAGE_EMPRESAS))
):
    """
    Desactiva (cambia el estado a inactivo) una Empresa por su ID.
    Solo accesible por usuarios con permisos de gestión de empresas.
    """
    # Obtener la empresa por ID
    db_empresa = db.query(DBEmpresa).filter(DBEmpresa.empresa_id == empresa_id).first()
    if db_empresa is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Empresa no encontrada.")

    if db_empresa.estado == EstadoEnum.inactivo:
         raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="La empresa ya está inactiva.")

    db_empresa.estado = EstadoEnum.inactivo

    db.commit() 

    return {} 

@router.patch("/{empresa_id}", response_model=Empresa) # Retorna el esquema Empresa
def activate_empresa(
    empresa_id: int,
    db: Session = Depends(get_db),
    current_user: auth_utils.Usuario = Depends(auth_utils.get_current_active_user_with_role(ROLES_CAN_MANAGE_EMPRESAS))
):
    """
    Activa (cambia el estado a activo) una Empresa por su ID.
    Solo accesible por usuarios con permisos de gestión de empresas.
    """
    # Obtener la empresa por ID
    db_empresa = db.query(DBEmpresa).filter(DBEmpresa.empresa_id == empresa_id).first()

    if db_empresa is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Empresa no encontrada.")

    if db_empresa.estado == EstadoEnum.activo:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="La empresa ya está activa.")

    db_empresa.estado = EstadoEnum.activo

    db.commit()
    db.refresh(db_empresa)

    return db_empresa
