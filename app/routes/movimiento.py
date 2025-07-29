from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session, joinedload
from typing import List

from ..database import get_db
from .. import auth as auth_utils # Importación corregida

# Importaciones siguiendo el patrón del proyecto
from ..models.producto import Producto as DBProducto
from ..models.movimiento import MovimientoInventario as DBMovimientoInventario
from ..schemas.movimiento import MovimientoCreate, MovimientoResponse

router = APIRouter(
    prefix="/movimientos",
    tags=["Movimientos de Inventario"]
)

# Roles que pueden gestionar movimientos de inventario
ROLES_CAN_MANAGE_MOVEMENTS = ["Administrador", "Empleado"]

@router.post("/", response_model=MovimientoResponse, status_code=status.HTTP_201_CREATED)
def create_movimiento(
    movimiento: MovimientoCreate,
    db: Session = Depends(get_db),
    current_user: auth_utils.Usuario = Depends(auth_utils.get_current_active_user_with_role(ROLES_CAN_MANAGE_MOVEMENTS)) # Dependencia corregida
):
    db_product = db.query(DBProducto).filter(DBProducto.producto_id == movimiento.producto_id).first()
    if not db_product:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Producto no encontrado")

    stock_anterior = db_product.stock
    new_stock = stock_anterior

    if movimiento.tipo_movimiento in ["merma", "ajuste_negativo", "uso_interno"]:
        if stock_anterior < movimiento.cantidad:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No hay suficiente stock para realizar este movimiento")
        new_stock -= movimiento.cantidad
    elif movimiento.tipo_movimiento == "ajuste_positivo":
        new_stock += movimiento.cantidad
    else:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Tipo de movimiento inválido")

    # Actualizar el stock del producto
    db_product.stock = new_stock
    db.add(db_product)
    db.flush() # Para que el stock_nuevo esté actualizado antes de crear el movimiento

    # Crear el registro de movimiento
    db_movimiento = DBMovimientoInventario(
        **movimiento.model_dump(),
        usuario_id=current_user.usuario_id,
        stock_anterior=stock_anterior,
        stock_nuevo=new_stock
    )
    db.add(db_movimiento)
    db.commit()
    db.refresh(db_movimiento)

    return db_movimiento

@router.get("/", response_model=List[MovimientoResponse])
def read_movimientos(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    current_user: auth_utils.Usuario = Depends(auth_utils.get_current_active_user_with_role(ROLES_CAN_MANAGE_MOVEMENTS)) # Dependencia corregida
):
    movimientos = db.query(DBMovimientoInventario).options(joinedload(DBMovimientoInventario.producto), joinedload(DBMovimientoInventario.usuario)).offset(skip).limit(limit).all()
    return movimientos
