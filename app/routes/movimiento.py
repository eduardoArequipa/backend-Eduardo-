from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session, joinedload
from typing import List, Optional
from decimal import Decimal

from ..database import get_db
from .. import auth as auth_utils # Importación corregida

# Importaciones siguiendo el patrón del proyecto
from ..models.producto import Producto as DBProducto
from ..models.movimiento import MovimientoInventario as DBMovimientoInventario
from ..models.enums import TipoMovimientoEnum
from ..schemas.movimiento import MovimientoCreate, MovimientoResponse, MovimientoPagination

router = APIRouter(
    prefix="/movimientos",
    tags=["Movimientos de Inventario"]
)


@router.post("/", response_model=MovimientoResponse, status_code=status.HTTP_201_CREATED)
def create_movimiento(
    movimiento: MovimientoCreate,
    db: Session = Depends(get_db),
    current_user: auth_utils.Usuario = Depends(auth_utils.require_menu_access("/movimientos"))
):
    # Validaciones de negocio mejoradas
    if movimiento.cantidad <= 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="La cantidad debe ser mayor a cero"
        )

    if movimiento.tipo_movimiento not in TipoMovimientoEnum:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Tipo de movimiento inválido"
        )

    db_product = db.query(DBProducto).filter(DBProducto.producto_id == movimiento.producto_id).first()
    if not db_product:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Producto no encontrado")

    stock_anterior = Decimal(str(db_product.stock))
    new_stock = stock_anterior

    if movimiento.tipo_movimiento in [TipoMovimientoEnum.merma, TipoMovimientoEnum.ajuste_negativo, TipoMovimientoEnum.uso_interno]:
        if stock_anterior < movimiento.cantidad:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Stock insuficiente. Stock actual: {stock_anterior}, cantidad solicitada: {movimiento.cantidad}"
            )
        new_stock -= movimiento.cantidad
    elif movimiento.tipo_movimiento == TipoMovimientoEnum.ajuste_positivo:
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

@router.get("/", response_model=MovimientoPagination)
def read_movimientos(
    skip: int = Query(0, ge=0, description="Número de registros a omitir"),
    limit: int = Query(10, gt=0, le=100, description="Número máximo de registros a devolver"),
    producto_id: Optional[int] = Query(None, description="Filtrar por ID del producto"),
    tipo_movimiento: Optional[TipoMovimientoEnum] = Query(None, description="Filtrar por tipo de movimiento"),
    search: Optional[str] = Query(None, description="Buscar en el motivo del movimiento"),
    db: Session = Depends(get_db),
    current_user: auth_utils.Usuario = Depends(auth_utils.require_menu_access("/movimientos"))
):
    # Construir la consulta base
    query = db.query(DBMovimientoInventario)

    # Aplicar filtros opcionales
    if producto_id:
        query = query.filter(DBMovimientoInventario.producto_id == producto_id)

    if tipo_movimiento:
        query = query.filter(DBMovimientoInventario.tipo_movimiento == tipo_movimiento)

    if search:
        query = query.filter(DBMovimientoInventario.motivo.ilike(f"%{search}%"))

    # Obtener el total de registros (antes de aplicar paginación)
    total = query.count()

    # Aplicar paginación y cargar relaciones
    movimientos = query.options(
        joinedload(DBMovimientoInventario.producto),
        joinedload(DBMovimientoInventario.usuario)
    ).order_by(DBMovimientoInventario.fecha_movimiento.desc()).offset(skip).limit(limit).all()

    return {
        "items": movimientos,
        "total": total
    }
