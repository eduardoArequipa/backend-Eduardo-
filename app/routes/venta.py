from typing import List, Optional
from datetime import datetime
from decimal import Decimal
from fastapi import APIRouter, Depends, HTTPException, status, Query, Path
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import or_

from .. import auth as auth_utils
from ..database import get_db
from ..models.venta import Venta as DBVenta
from ..models.detalle_venta import DetalleVenta as DBDetalleVenta
from ..models.producto import Producto as DBProducto
from ..models.metodo_pago import MetodoPago as DBMetodoPago
from ..models.usuario import Usuario as DBUsuario
from ..models.persona import Persona as DBPersona
from ..models.enums import EstadoVentaEnum, EstadoEnum
from ..schemas.producto import Producto
# Importar los esquemas actualizados
from ..schemas.venta import Venta, VentaCreate, ProductoSchemaBase, VentaPagination
from ..services.facturacion_service import crear_factura_tesabiz

router = APIRouter(
    prefix="/ventas",
    tags=["ventas"]
)

# Router para productos (accesible públicamente si es necesario, o se puede integrar en el principal)
router_productos_public = APIRouter(
    prefix="/productos",
    tags=["productos (app-friendly)"]
)

def get_venta_or_404(
    venta_id: int = Path(..., title="El ID de la venta"),
    db: Session = Depends(get_db)
) -> DBVenta:
    """
    Dependencia para obtener una venta por ID con todas sus relaciones precargadas.
    """
    venta = db.query(DBVenta).options(
        joinedload(DBVenta.persona),
        joinedload(DBVenta.metodo_pago),
        joinedload(DBVenta.creador),
        joinedload(DBVenta.modificador),
        joinedload(DBVenta.detalles).joinedload(DBDetalleVenta.producto),
        joinedload(DBVenta.factura_electronica)
    ).filter(DBVenta.venta_id == venta_id).first()
    if venta is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Venta no encontrada.")
    return venta

def calcular_stock_en_unidad_minima(producto: DBProducto, cantidad_vendida: Decimal, presentacion_venta: str) -> Decimal:
    """
    Calcula la cantidad de stock a descontar en la unidad mínima de inventario.
    
    Args:
        producto: El producto de la base de datos con sus conversiones precargadas
        cantidad_vendida: La cantidad que se vendió en la presentación específica
        presentacion_venta: El nombre de la presentación en la que se vendió
    
    Returns:
        Decimal: La cantidad a descontar del stock en unidad mínima
    """
    # Si se vende en "Unidad" (unidad mínima), no hay conversión necesaria
    if not presentacion_venta or presentacion_venta == 'Unidad':
        return cantidad_vendida
    
    # Buscar la conversión correspondiente y verificar que sea para venta
    presentacion_nombre = presentacion_venta.strip()
    conversion = None
    
    for c in producto.conversiones:
        # AÑADIDO: Verificar que la conversión esté habilitada para venta
        if c.nombre_presentacion.lower() == presentacion_nombre.lower() and c.es_para_venta:
            conversion = c
            break
    
    if not conversion:
        # Si no se encuentra la conversión o no está habilitada para venta, lanzar un error
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"La presentación de venta '{presentacion_venta}' no es válida o no está habilitada para ventas en el producto '{producto.nombre}'."
        )
    
    # Asegurarse de que el factor de conversión no sea cero
    if conversion.unidades_por_presentacion <= 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"El factor de conversión para la presentación '{presentacion_venta}' del producto '{producto.nombre}' es cero o negativo."
        )

    # Calcular la cantidad en unidad mínima
    stock_a_descontar = cantidad_vendida * conversion.unidades_por_presentacion
    
    return stock_a_descontar

@router_productos_public.get("/buscar_por_codigo/{codigo_producto}", response_model=Producto)
def get_producto_by_codigo(
    codigo_producto: str = Path(..., description="Código único del producto"),
    db: Session = Depends(get_db)
):
    """
    Busca un producto por su código y devuelve su información básica.
    """
    db_producto = db.query(DBProducto).filter(
        DBProducto.codigo == codigo_producto,
        DBProducto.estado == EstadoEnum.activo
    ).first()
    if db_producto is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Producto no encontrado o inactivo.")
    return db_producto

@router.post("/", response_model=Venta, status_code=status.HTTP_201_CREATED)
async def create_venta(
    venta_data: VentaCreate,
    db: Session = Depends(get_db),
    current_user: auth_utils.Usuario = Depends(auth_utils.require_menu_access("/ventas"))
):
    """
    Crea una nueva venta, valida stock y actualiza existencias de productos.
    Si se solicita, llama al servicio de facturación electrónica.
    """
    db.begin_nested()
    try:
        if venta_data.persona_id:
            persona = db.query(DBPersona).filter(DBPersona.persona_id == venta_data.persona_id, DBPersona.estado == EstadoEnum.activo).first()
            if not persona:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Cliente con ID {venta_data.persona_id} no encontrado o inactivo.")

        if not venta_data.detalles:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="La venta debe tener al menos un producto.")

        total_venta = sum(Decimal(str(d.cantidad)) * Decimal(str(d.precio_unitario)) for d in venta_data.detalles)

        nueva_venta = DBVenta(
            persona_id=venta_data.persona_id,
            total=total_venta,
            metodo_pago_id=venta_data.metodo_pago_id,
            estado=venta_data.estado,
            creado_por=current_user.usuario_id,
            modificado_por=current_user.usuario_id,
            detalles=[DBDetalleVenta(**d.model_dump()) for d in venta_data.detalles]
        )
        db.add(nueva_venta)
        db.flush()

        for detalle_data in venta_data.detalles:
            producto = db.query(DBProducto).options(joinedload(DBProducto.conversiones)).filter(DBProducto.producto_id == detalle_data.producto_id).first()
            stock_a_descontar = calcular_stock_en_unidad_minima(producto, Decimal(str(detalle_data.cantidad)), getattr(detalle_data, 'presentacion_venta', 'Unidad'))
            
            if producto.stock < stock_a_descontar:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Stock insuficiente para el producto '{producto.nombre}'.")
            
            producto.stock -= stock_a_descontar
            db.add(producto)

        db.commit()
        db.refresh(nueva_venta)

        # --- Lógica de Facturación Condicional ---
        if venta_data.solicitar_factura:
            if not venta_data.persona_id:
                # Esta validación es crucial. Si se pide factura, el cliente es obligatorio.
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Se debe seleccionar un cliente para poder emitir una factura.")
            try:
                print(f"Iniciando proceso de facturación para la venta ID: {nueva_venta.venta_id}")
                await crear_factura_tesabiz(nueva_venta.venta_id, db)
                print(f"Proceso de facturación para la venta ID: {nueva_venta.venta_id} completado.")
            except Exception as e:
                # La venta se creó, pero la facturación falló. Se registra el error pero no se anula la transacción.
                print(f"ALERTA: La venta {nueva_venta.venta_id} se creó exitosamente, pero falló la facturación electrónica: {e}")
        
        return get_venta_or_404(nueva_venta.venta_id, db)

    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        print(f"ERROR al crear la venta: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Ocurrió un error inesperado al crear la Venta: {str(e)}")


@router.get("/", response_model=VentaPagination)
def read_ventas(
    estado: Optional[EstadoVentaEnum] = Query(None, description="Filtrar por estado de la venta"),
    persona_id: Optional[int] = Query(None, description="Filtrar por ID de la persona asociada a la venta"),
    metodo_pago_id: Optional[int] = Query(None, description="Filtrar por ID del método de pago"),
    fecha_desde: Optional[datetime] = Query(None, description="Fecha de inicio del rango de búsqueda (inclusive)"),
    fecha_hasta: Optional[datetime] = Query(None, description="Fecha de fin del rango de búsqueda (inclusive)"),
    search: Optional[str] = Query(None, description="Buscar por nombre/apellido de persona o nombre de producto"),
    skip: int = Query(0, ge=0), 
    limit: int = Query(10, gt=0),
    db: Session = Depends(get_db),
    current_user: auth_utils.Usuario = Depends(auth_utils.require_menu_access("/ventas"))
):
    """
    Obtiene una lista paginada de ventas con opciones de filtrado y búsqueda.
    """
    query = db.query(DBVenta)

    if estado: query = query.filter(DBVenta.estado == estado)
    if persona_id: query = query.filter(DBVenta.persona_id == persona_id)
    if metodo_pago_id: query = query.filter(DBVenta.metodo_pago_id == metodo_pago_id)
    if fecha_desde: query = query.filter(DBVenta.fecha_venta >= fecha_desde)
    if fecha_hasta: query = query.filter(DBVenta.fecha_venta <= fecha_hasta)
    
    if search:
        search_pattern = f"%{search}%"
        query = query.join(DBVenta.persona).outerjoin(DBVenta.detalles).join(DBDetalleVenta.producto).filter(or_(
            DBPersona.nombre.ilike(search_pattern),
            DBPersona.apellido_paterno.ilike(search_pattern),
            DBPersona.apellido_materno.ilike(search_pattern),
            DBProducto.nombre.ilike(search_pattern)
        )).distinct()

    total = query.count()
    
    ventas = query.options(
        joinedload(DBVenta.persona),
        joinedload(DBVenta.metodo_pago), 
        joinedload(DBVenta.creador), 
        joinedload(DBVenta.modificador),
        joinedload(DBVenta.detalles).joinedload(DBDetalleVenta.producto)
    ).order_by(DBVenta.venta_id.desc()).offset(skip).limit(limit).all()

    return {
        "items": ventas,
        "total": total
    }

@router.get("/{venta_id}", response_model=Venta)
def get_venta(
    venta: DBVenta = Depends(get_venta_or_404),
    current_user: auth_utils.Usuario = Depends(auth_utils.require_menu_access("/ventas"))
):
    """
    Obtiene los detalles de una venta específica por su ID.
    """
    return venta

@router.patch("/{venta_id}/anular", response_model=Venta)
def anular_venta(
    db_venta: DBVenta = Depends(get_venta_or_404),
    db: Session = Depends(get_db),
    current_user: auth_utils.Usuario = Depends(auth_utils.require_menu_access("/ventas"))
):
    """
    Anula una venta existente y repone el stock de los productos involucrados,
    utilizando la lógica de conversión de unidades de forma robusta.
    """
    if db_venta.estado == EstadoVentaEnum.anulada:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="La venta ya está anulada.")
    
    db.begin_nested()
    try:
        # Precargar productos y sus conversiones para eficiencia
        product_ids = [d.producto_id for d in db_venta.detalles]
        products_map = {
            p.producto_id: p for p in db.query(DBProducto).options(
                joinedload(DBProducto.conversiones)
            ).filter(DBProducto.producto_id.in_(product_ids)).all()
        }

        for detalle in db_venta.detalles:
            producto = products_map.get(detalle.producto_id)
            if not producto:
                continue

            # --- Lógica de Conversión Inversa ---
            presentacion_venta = getattr(detalle, 'presentacion_venta', 'Unidad')
            stock_a_reponer = calcular_stock_en_unidad_minima(
                producto,
                Decimal(str(detalle.cantidad)),
                presentacion_venta
            )
            
            producto.stock = (producto.stock or 0) + stock_a_reponer
            producto.modificado_por = current_user.usuario_id
            db.add(producto)
            
            print(f"Stock repuesto para '{producto.nombre}': "
                  f"Anterior: {(producto.stock or 0) - stock_a_reponer}, "
                  f"Nuevo: {producto.stock}, "
                  f"Repuesto: {stock_a_reponer}")

        db_venta.estado = EstadoVentaEnum.anulada
        db_venta.modificado_por = current_user.usuario_id
        db.add(db_venta)

        db.commit()
        db.refresh(db_venta)
        return get_venta_or_404(db_venta.venta_id, db)
        
    except Exception as e:
        db.rollback()
        print(f"ERROR al anular la venta: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Ocurrió un error al anular la venta: {str(e)}")