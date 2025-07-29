from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query, Path, Response
from sqlalchemy.orm import Session
from sqlalchemy import or_

from .. import auth as auth_utils
from ..database import get_db
from ..models.unidad_medida import UnidadMedida as DBUnidadMedida
from ..models.enums import EstadoEnum
from ..schemas.unidad_medida import UnidadMedida, UnidadMedidaCreate

router = APIRouter(
    prefix="/unidades-medida",
    tags=["unidades-medida"]
)

ROLES_CAN_MANAGE_UNIDADES_MEDIDA = ["Administrador", "Empleado"]

def get_unidad_medida_or_404(
    unidad_id: int = Path(..., title="El ID de la unidad de medida"),
    db: Session = Depends(get_db)
) -> DBUnidadMedida:
    """
    Dependencia para obtener una unidad de medida por su ID.
    Lanza un error 404 si no se encuentra.
    """
    unidad_medida = db.query(DBUnidadMedida).filter(DBUnidadMedida.unidad_id == unidad_id).first()
    if unidad_medida is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unidad de medida no encontrada.")
    return unidad_medida

@router.post("/", response_model=UnidadMedida, status_code=status.HTTP_201_CREATED)
def create_unidad_medida(
    unidad_medida: UnidadMedidaCreate,
    db: Session = Depends(get_db),
    current_user: auth_utils.Usuario = Depends(auth_utils.get_current_active_user_with_role(ROLES_CAN_MANAGE_UNIDADES_MEDIDA))
):
    db_unidad_existente = db.query(DBUnidadMedida).filter(
        or_(DBUnidadMedida.nombre_unidad == unidad_medida.nombre_unidad, DBUnidadMedida.abreviatura == unidad_medida.abreviatura)
    ).first()
    if db_unidad_existente:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Ya existe una unidad de medida con este nombre o abreviatura.")

    new_unidad_medida = DBUnidadMedida(**unidad_medida.model_dump())
    db.add(new_unidad_medida)
    db.commit()
    db.refresh(new_unidad_medida)
    return new_unidad_medida

@router.get("/", response_model=List[UnidadMedida])
def read_unidades_medida(
    estado: Optional[EstadoEnum] = Query(None, description="Filtrar por estado"),
    search: Optional[str] = Query(None, description="Texto de búsqueda por nombre o abreviatura"),
    skip: int = Query(0, ge=0), limit: int = Query(100, gt=0),
    db: Session = Depends(get_db),
    current_user: auth_utils.Usuario = Depends(auth_utils.get_current_active_user_with_role(ROLES_CAN_MANAGE_UNIDADES_MEDIDA))
):
    query = db.query(DBUnidadMedida)
    if estado: query = query.filter(DBUnidadMedida.estado == estado)
    if search:
        query = query.filter(or_(
            DBUnidadMedida.nombre_unidad.ilike(f"%{search}%"),
            DBUnidadMedida.abreviatura.ilike(f"%{search}%")
        ))
    return query.offset(skip).limit(limit).all()

@router.get("/{unidad_id}", response_model=UnidadMedida)
def read_unidad_medida(
    unidad_medida: DBUnidadMedida = Depends(get_unidad_medida_or_404),
    current_user: auth_utils.Usuario = Depends(auth_utils.get_current_active_user_with_role(ROLES_CAN_MANAGE_UNIDADES_MEDIDA))
):
    return unidad_medida

@router.put("/{unidad_id}", response_model=UnidadMedida)
def update_unidad_medida(
    unidad_medida_update: UnidadMedidaCreate,
    db_unidad_medida: DBUnidadMedida = Depends(get_unidad_medida_or_404),
    db: Session = Depends(get_db),
    current_user: auth_utils.Usuario = Depends(auth_utils.get_current_active_user_with_role(ROLES_CAN_MANAGE_UNIDADES_MEDIDA))
):
    update_data = unidad_medida_update.model_dump(exclude_unset=True)
    
    nombre_updated = update_data.get('nombre_unidad')
    abrev_updated = update_data.get('abreviatura')

    if nombre_updated or abrev_updated:
        query_filter = []
        if nombre_updated and nombre_updated != db_unidad_medida.nombre_unidad:
            query_filter.append(DBUnidadMedida.nombre_unidad == nombre_updated)
        if abrev_updated and abrev_updated != db_unidad_medida.abreviatura:
            query_filter.append(DBUnidadMedida.abreviatura == abrev_updated)
        
        if query_filter:
            existing = db.query(DBUnidadMedida).filter(or_(*query_filter)).first()
            if existing and existing.unidad_id != db_unidad_medida.unidad_id:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Ya existe otra unidad de medida con este nombre o abreviatura.")

    for field, value in update_data.items():
        setattr(db_unidad_medida, field, value)
    
    db.commit()
    db.refresh(db_unidad_medida)
    return db_unidad_medida

@router.delete("/{unidad_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_unidad_medida(
    db_unidad_medida: DBUnidadMedida = Depends(get_unidad_medida_or_404),
    db: Session = Depends(get_db),
    current_user: auth_utils.Usuario = Depends(auth_utils.get_current_active_user_with_role(ROLES_CAN_MANAGE_UNIDADES_MEDIDA))
):
    if db_unidad_medida.estado == EstadoEnum.inactivo:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="La unidad de medida ya está inactiva.")
    
    db_unidad_medida.estado = EstadoEnum.inactivo
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)

@router.patch("/{unidad_id}/activar", response_model=UnidadMedida)
def activate_unidad_medida(
    db_unidad_medida: DBUnidadMedida = Depends(get_unidad_medida_or_404),
    db: Session = Depends(get_db),
    current_user: auth_utils.Usuario = Depends(auth_utils.get_current_active_user_with_role(ROLES_CAN_MANAGE_UNIDADES_MEDIDA))
):
    if db_unidad_medida.estado == EstadoEnum.activo:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="La unidad de medida ya está activa.")

    db_unidad_medida.estado = EstadoEnum.activo
    db.commit()
    db.refresh(db_unidad_medida)
    return db_unidad_medida
