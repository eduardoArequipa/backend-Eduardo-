from typing import List, Optional
from datetime import datetime
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import or_

# Importa tus utilidades de auth y la dependencia get_db
from .. import auth as auth_utils
from ..database import get_db

# Importa los modelos SQLAlchemy
from ..models.venta import Venta as DBVenta
from ..models.detalle_venta import DetalleVenta as DBDetalleVenta
from ..models.producto import Producto as DBProducto
from ..models.cliente import Cliente as DBCliente
from ..models.metodo_pago import MetodoPago as DBMetodoPago
from ..models.usuario import Usuario as DBUsuario
from ..models.persona import Persona as DBPersona
from ..models.enums import EstadoVentaEnum, EstadoEnum

# Importa tus esquemas Pydantic
from ..schemas.venta import (
    Venta,
    VentaCreate,
    VentaUpdate,
    DetalleVentaCreate,
    DetalleVenta,
    ProductoSchemaBase # Importa el nuevo esquema de producto
)
from ..schemas.cliente import ClienteNested
from ..schemas.usuario import UsuarioAudit
from ..schemas.metodo_pago import MetodoPagoNested
# Ya no necesitamos importar ProductoNested directamente de schemas.producto aquí si usamos ProductoSchemaBase


router = APIRouter(
    prefix="/ventas",
    tags=["ventas"]
)

router_productos_public = APIRouter( # Nuevo router para endpoints de productos públicos/para app
    prefix="/productos",
    tags=["productos (app-friendly)"]
)


ROLES_CAN_MANAGE_VENTAS = ["Administrador", "Empleado"]

# --- NUEVO: Endpoint para buscar producto por código de barras (para la app) ---
@router_productos_public.get("/buscar_por_codigo/{codigo_producto}", response_model=ProductoSchemaBase)
def get_producto_by_codigo(
    codigo_producto: str,
    db: Session = Depends(get_db)
    # No requiere autenticación si es para escanear en un TPV, o puedes añadirla si es para empleados logueados
):
    """
    Busca un producto por su código de barras (código único)
    y retorna su información esencial para la app (precio, stock, etc.).
    """
    db_producto = db.query(DBProducto).filter(
        DBProducto.codigo == codigo_producto,
        DBProducto.estado == EstadoEnum.activo
    ).first()

    if db_producto is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Producto no encontrado o inactivo.")

    return db_producto


# --- Endpoint para Crear una Nueva Venta (EXISTENTE, CON PEQUEÑAS MEJORAS) ---
@router.post("/", response_model=Venta, status_code=status.HTTP_201_CREATED)
def create_venta(
    venta_data: VentaCreate,
    db: Session = Depends(get_db),
    current_user: auth_utils.Usuario = Depends(auth_utils.get_current_active_user_with_role(ROLES_CAN_MANAGE_VENTAS))
):
    """
    Crea una nueva Venta con sus detalles y **resta el stock de los productos**.
    Ideal para ser usada tanto por el sistema web como por la app móvil
    (la app enviará los detalles de un 'carrito' local).

    NOTA IMPORTANTE SOBRE STOCK:
    CONFIRMACIÓN: Ya que la lógica de stock se maneja aquí en Python de forma transaccional,
    es FUNDAMENTAL deshabilitar o eliminar los triggers de la base de datos
    `trg_actualizar_stock_venta` y `trg_actualizar_stock_devolucion`
    para evitar doble deducción/adición de stock. El trigger de compra (`trg_actualizar_stock_compra`)
    debe ser revisado si tu endpoint de creación de compras también maneja stock.
    """
    db.begin_nested()

    try:
        db_cliente = None
        if venta_data.cliente_id:
            db_cliente = db.query(DBCliente).filter(
                DBCliente.cliente_id == venta_data.cliente_id,
                DBCliente.estado == EstadoEnum.activo
            ).first()
            if db_cliente is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Cliente con ID {venta_data.cliente_id} no encontrado o inactivo.")

        db_metodo_pago = db.query(DBMetodoPago).filter(
            DBMetodoPago.metodo_pago_id == venta_data.metodo_pago_id,
            DBMetodoPago.estado == EstadoEnum.activo
        ).first()
        if db_metodo_pago is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Método de pago con ID {venta_data.metodo_pago_id} no encontrado o inactivo.")

        if not venta_data.detalles:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="La venta debe tener al menos un detalle.")

        total_venta = Decimal(0)
        db_detalles = []
        productos_a_actualizar_stock = {}

        for detalle_data in venta_data.detalles:
            db_producto = db.query(DBProducto).filter(
                DBProducto.producto_id == detalle_data.producto_id,
                DBProducto.estado == EstadoEnum.activo
            ).first()
            if db_producto is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Producto con ID {detalle_data.producto_id} en el detalle no encontrado o inactivo.")

            if detalle_data.cantidad <= 0:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"La cantidad para el producto ID {detalle_data.producto_id} debe ser positiva.")
            
            # **Validación de precio unitario**
            # Puedes decidir si el precio_unitario enviado debe coincidir con el precio_actual del producto en DB
            # o si el precio_unitario enviado es el precio final de la venta (útil para descuentos).
            # Por ahora, mantendremos la validación de que sea positivo.
            if detalle_data.precio_unitario < 0:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"El precio unitario para el producto ID {detalle_data.producto_id} no puede ser negativo.")

            # Verificar stock disponible antes de la venta
            if (db_producto.stock or 0) < detalle_data.cantidad:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Stock insuficiente para el producto '{db_producto.nombre}' (ID: {detalle_data.producto_id}). Stock actual: {db_producto.stock or 0}, Cantidad solicitada: {detalle_data.cantidad}.")

            subtotal_detalle = Decimal(str(detalle_data.cantidad)) * Decimal(str(detalle_data.precio_unitario))
            total_venta += subtotal_detalle

            db_detalle = DBDetalleVenta(
                producto_id=detalle_data.producto_id,
                cantidad=detalle_data.cantidad,
                precio_unitario=detalle_data.precio_unitario
            )
            db_detalles.append(db_detalle)

            productos_a_actualizar_stock[detalle_data.producto_id] = productos_a_actualizar_stock.get(detalle_data.producto_id, 0) + detalle_data.cantidad

        nueva_venta = DBVenta(
            cliente_id=venta_data.cliente_id,
            total=total_venta,
            metodo_pago_id=venta_data.metodo_pago_id,
            estado=venta_data.estado,
            creado_por=current_user.usuario_id,
            modificado_por=current_user.usuario_id
        )

        nueva_venta.detalles.extend(db_detalles)

        db.add(nueva_venta)
        db.flush()

        for producto_id, cantidad_vendida in productos_a_actualizar_stock.items():
            db_producto = db.query(DBProducto).filter(DBProducto.producto_id == producto_id).first()
            if db_producto:
                db_producto.stock = (db_producto.stock or 0) - cantidad_vendida
                db_producto.modificado_por = current_user.usuario_id
                db.add(db_producto)

        db.commit()

        db_venta_for_response = db.query(DBVenta).options(
            joinedload(DBVenta.cliente).joinedload(DBCliente.persona),
            joinedload(DBVenta.metodo_pago),
            joinedload(DBVenta.creador),
            joinedload(DBVenta.modificador),
            joinedload(DBVenta.detalles).joinedload(DBDetalleVenta.producto)
        ).filter(DBVenta.venta_id == nueva_venta.venta_id).first()

        return db_venta_for_response

    except HTTPException as e:
        db.rollback()
        raise e
    except Exception as e:
        db.rollback()
        print(f"Error durante la creación de Venta: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Ocurrió un error al crear la Venta.")


# --- Endpoint para Listar Ventas (SIN CAMBIOS) ---
@router.get("/", response_model=List[Venta])
def read_ventas(
    estado: Optional[EstadoVentaEnum] = Query(None, description="Filtrar por estado de venta"),
    cliente_id: Optional[int] = Query(None, description="Filtrar por ID de cliente"),
    metodo_pago_id: Optional[int] = Query(None, description="Filtrar por ID de método de pago"),
    fecha_desde: Optional[datetime] = Query(None, description="Filtrar ventas desde esta fecha (inclusive)"),
    fecha_hasta: Optional[datetime] = Query(None, description="Filtrar ventas hasta esta fecha (inclusive)"),
    search: Optional[str] = Query(None, description="Texto de búsqueda por nombre de cliente o nombre de producto"),
    skip: int = Query(0, ge=0, description="Número de elementos a omitir (paginación)"),
    limit: int = Query(100, gt=0, description="Número máximo de elementos a retornar (paginación)"),
    db: Session = Depends(get_db),
    current_user: auth_utils.Usuario = Depends(auth_utils.get_current_active_user_with_role(ROLES_CAN_MANAGE_VENTAS))
):
    """
    Obtiene una lista de Ventas con opciones de filtro, búsqueda y paginación.
    Incluye usuario, cliente, método de pago, creador, modificador y detalles con productos.
    Accesible solo por usuarios con permisos de gestión de ventas.
    """
    query = db.query(DBVenta).options(
        joinedload(DBVenta.cliente).joinedload(DBCliente.persona),
        joinedload(DBVenta.metodo_pago),
        joinedload(DBVenta.creador),
        joinedload(DBVenta.modificador),
        joinedload(DBVenta.detalles).joinedload(DBDetalleVenta.producto)
    )

    if estado:
        query = query.filter(DBVenta.estado == estado)
    if cliente_id is not None:
        query = query.filter(DBVenta.cliente_id == cliente_id)
    if metodo_pago_id is not None:
        query = query.filter(DBVenta.metodo_pago_id == metodo_pago_id)
    if fecha_desde:
        query = query.filter(DBVenta.fecha_venta >= fecha_desde)
    if fecha_hasta:
        query = query.filter(DBVenta.fecha_venta <= fecha_hasta)

    if search:
        query = query.filter(
            or_(
                DBVenta.cliente.has(
                    DBCliente.persona.has(
                        or_(
                            DBPersona.nombre.ilike(f"%{search}%"),
                            DBPersona.apellido_paterno.ilike(f"%{search}%"),
                            DBPersona.apellido_materno.ilike(f"%{search}%")
                        )
                    )
                ),
                DBVenta.detalles.any(
                    DBDetalleVenta.producto.has(
                        DBProducto.nombre.ilike(f"%{search}%")
                    )
                )
            )
        )

    ventas = query.offset(skip).limit(limit).all()
    return ventas


# --- Endpoint para Obtener una Venta por ID (SIN CAMBIOS) ---
@router.get("/{venta_id}", response_model=Venta)
def get_venta(
    venta_id: int,
    db: Session = Depends(get_db),
    current_user: auth_utils.Usuario = Depends(auth_utils.get_current_active_user_with_role(ROLES_CAN_MANAGE_VENTAS))
):
    """
    Obtiene una venta específica por su ID, incluyendo todos sus detalles y relaciones.
    Solo accesible por usuarios con permisos de gestión de ventas.
    """
    db_venta = db.query(DBVenta).options(
        joinedload(DBVenta.cliente).joinedload(DBCliente.persona),
        joinedload(DBVenta.metodo_pago),
        joinedload(DBVenta.creador),
        joinedload(DBVenta.modificador),
        joinedload(DBVenta.detalles).joinedload(DBDetalleVenta.producto)
    ).filter(DBVenta.venta_id == venta_id).first()

    if db_venta is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Venta no encontrada.")

    return db_venta


# --- Endpoint para Anular una Venta (PATCH /ventas/{venta_id}/anular) (SIN CAMBIOS) ---
@router.patch("/{venta_id}/anular", response_model=Venta)
def anular_venta(
    venta_id: int,
    db: Session = Depends(get_db),
    current_user: auth_utils.Usuario = Depends(auth_utils.get_current_active_user_with_role(ROLES_CAN_MANAGE_VENTAS))
):
    """
    Anula una Venta por su ID y **aumenta el stock de los productos asociados**.
    Solo accesible por usuarios con permisos de gestión de ventas.
    """
    db_venta = db.query(DBVenta).options(
        joinedload(DBVenta.cliente).joinedload(DBCliente.persona),
        joinedload(DBVenta.metodo_pago),
        joinedload(DBVenta.creador),
        joinedload(DBVenta.modificador),
        joinedload(DBVenta.detalles).joinedload(DBDetalleVenta.producto)
    ).filter(DBVenta.venta_id == venta_id).first()

    if db_venta is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Venta no encontrada.")

    if db_venta.estado == EstadoVentaEnum.anulada:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="La venta ya está anulada.")

    try:
        db.begin_nested()

        for detalle in db_venta.detalles:
            db_producto = db.query(DBProducto).filter(DBProducto.producto_id == detalle.producto_id).first()
            if db_producto:
                db_producto.stock = (db_producto.stock or 0) + detalle.cantidad
                db_producto.modificado_por = current_user.usuario_id
                db.add(db_producto)

        db_venta.estado = EstadoVentaEnum.anulada
        db_venta.modificado_por = current_user.usuario_id

        db.commit()
        db.refresh(db_venta)

        return db_venta

    except HTTPException as e:
        db.rollback()
        raise e
    except Exception as e:
        db.rollback()
        print(f"Error al anular venta {venta_id} y revertir stock: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Ocurrió un error al anular la venta y revertir el stock.")