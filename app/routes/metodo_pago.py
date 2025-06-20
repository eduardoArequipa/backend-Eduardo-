# Componente1_SistemaWeb/backEnd/app/routes/metodo_pago.py
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from typing import Optional, List # Importar List para response_model

from app.database import get_db # Tu dependencia para obtener la sesión de DB
from app.schemas.metodo_pago import MetodoPago, MetodoPagoCreate # Tus esquemas Pydantic
from app.models.metodo_pago import MetodoPago as DBMethPago # <--- Importamos el modelo SQLAlchemy directamente
from app.models.enums import EstadoEnum
router = APIRouter(
    prefix="/metodos_pago",
    tags=["Métodos de Pago"]
)

@router.get("/", response_model=List[MetodoPago]) # Usamos List para Pydantic v1, si estás en Pydantic v2 puedes usar list[MetodoPago]
def read_metodos_pago(
    skip: int = 0,
    limit: int = 100,
    estado: Optional[EstadoEnum] = Query(None, description="Filtrar por estado (activo/inactivo)"),
    db: Session = Depends(get_db)
):
    query = db.query(DBMethPago)
    if estado:
        query = query.filter(DBMethPago.estado == estado)
    metodos = query.offset(skip).limit(limit).all()
    return metodos

@router.get("/{metodo_pago_id}", response_model=MetodoPago)
def read_metodo_pago(
    metodo_pago_id: int,
    db: Session = Depends(get_db)
):
    metodo = db.query(DBMethPago).filter(DBMethPago.metodo_pago_id == metodo_pago_id).first()
    if not metodo:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Método de pago no encontrado")
    return metodo

@router.post("/", response_model=MetodoPago, status_code=status.HTTP_201_CREATED)
def create_new_metodo_pago(
    metodo_pago: MetodoPagoCreate,
    db: Session = Depends(get_db)
):
    # Verificar si ya existe un método de pago con el mismo nombre
    existing_metodo = db.query(DBMethPago).filter(DBMethPago.nombre_metodo == metodo_pago.nombre_metodo).first()
    if existing_metodo:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Ya existe un método de pago con ese nombre.")

    # Lógica de creación directamente aquí
    db_metodo_pago = DBMethPago(
        nombre_metodo=metodo_pago.nombre_metodo,
        estado=EstadoEnum.activo
    )
    db.add(db_metodo_pago)
    db.commit()
    db.refresh(db_metodo_pago)
    return db_metodo_pago