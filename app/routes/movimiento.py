from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session, joinedload
from typing import List, Optional
from decimal import Decimal
from ..database import get_db
from .. import auth as auth_utils # Importación corregida

router = APIRouter(
    prefix="/movimientos",
    tags=["Movimientos de Inventario"]
)

from ..database import get_db
from .. import auth as auth_utils

from ..models.producto import Producto as DBProducto
from ..models.movimiento import MovimientoInventario as DBMovimientoInventario
from ..models.detalle_movimiento import DetalleMovimientoInventario as DBDetalleMovimiento
from ..models.conversion import Conversion as DBConversion
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
    db_product = db.query(DBProducto).options(joinedload(DBProducto.unidad_inventario)).filter(DBProducto.producto_id == movimiento.producto_id).first()
    if not db_product:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Producto no encontrado")

    total_cantidad_base = Decimal('0')
    
    # 1. Calcular la cantidad total en la unidad base
    for item in movimiento.items:
        if item.conversion_id:
            conversion = db.query(DBConversion).filter(
                DBConversion.id == item.conversion_id,
                DBConversion.producto_id == movimiento.producto_id
            ).first()
            if not conversion:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"La presentación con id {item.conversion_id} no es válida para este producto."
                )
            total_cantidad_base += item.cantidad * conversion.unidades_por_presentacion
        else:
            # Es la unidad base
            total_cantidad_base += item.cantidad

    # 2. Validaciones sobre la cantidad total
    if total_cantidad_base <= 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="La cantidad total del movimiento debe ser mayor a cero."
        )

    # Validar que si la unidad de medida es 'Unidad', la cantidad total sea un número entero
    if db_product.unidad_inventario.nombre_unidad.lower() == 'unidad' and total_cantidad_base % 1 != 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"La cantidad total para productos medidos en 'Unidad' debe ser un número entero. Total calculado: {total_cantidad_base}"
        )

    # 3. Validar y calcular el nuevo stock
    stock_anterior = Decimal(str(db_product.stock))
    new_stock = stock_anterior

    if movimiento.tipo_movimiento in [TipoMovimientoEnum.merma, TipoMovimientoEnum.ajuste_negativo, TipoMovimientoEnum.uso_interno ]:
        if stock_anterior < total_cantidad_base:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Stock insuficiente. Stock actual: {stock_anterior}, cantidad solicitada: {total_cantidad_base}"
            )
        new_stock -= total_cantidad_base
    elif movimiento.tipo_movimiento == TipoMovimientoEnum.ajuste_positivo or movimiento.tipo_movimiento == TipoMovimientoEnum.devolucion:
        new_stock += total_cantidad_base
    else:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Tipo de movimiento inválido")

    try:
        # 4. Actualizar el stock del producto
        db_product.stock = new_stock
        db.add(db_product)

        # 5. Crear el registro de movimiento maestro
        db_movimiento = DBMovimientoInventario(
            producto_id=movimiento.producto_id,
            tipo_movimiento=movimiento.tipo_movimiento,
            motivo=movimiento.motivo,
            cantidad=total_cantidad_base, # Guardar la cantidad total en la unidad base
            usuario_id=current_user.usuario_id,
            stock_anterior=stock_anterior,
            stock_nuevo=new_stock
        )
        db.add(db_movimiento)
        db.flush() # Flush para obtener el ID del movimiento maestro

        # 6. Crear los registros de detalle
        for item in movimiento.items:
            db_detalle = DBDetalleMovimiento(
                movimiento_id=db_movimiento.movimiento_id,
                conversion_id=item.conversion_id,
                cantidad=item.cantidad
            )
            db.add(db_detalle)

        db.commit()
        db.refresh(db_movimiento)
        return db_movimiento

    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Ocurrió un error al guardar el movimiento: {str(e)}"
        )


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
        joinedload(DBMovimientoInventario.usuario),
        joinedload(DBMovimientoInventario.detalles).joinedload(DBDetalleMovimiento.conversion)
    ).order_by(DBMovimientoInventario.fecha_movimiento.desc()).offset(skip).limit(limit).all()

    return {
        "items": movimientos,
        "total": total
    }
