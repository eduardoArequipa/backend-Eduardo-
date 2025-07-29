# backEnd/app/routes/venta.py

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
# from ..models.cliente import Cliente as DBCliente # <-- ¡ELIMINADO! Ya no hay un modelo DBCliente separado
from ..models.metodo_pago import MetodoPago as DBMetodoPago
from ..models.usuario import Usuario as DBUsuario
from ..models.persona import Persona as DBPersona # Persona ahora es el "cliente" en el contexto de ventas
from ..models.enums import EstadoVentaEnum, EstadoEnum

# Importar los esquemas actualizados
from ..schemas.venta import Venta, VentaCreate,ProductoSchemaBase # Venta ya debería incluir PersonaRead y ProductoSchemaBase en sus detalles

router = APIRouter(
    prefix="/ventas",
    tags=["ventas"]
)

# Router para productos (accesible públicamente si es necesario, o se puede integrar en el principal)
router_productos_public = APIRouter(
    prefix="/productos",
    tags=["productos (app-friendly)"] # Renombrado para más claridad
)

ROLES_CAN_MANAGE_VENTAS = ["Administrador", "Empleado"]

def get_venta_or_404(
    venta_id: int = Path(..., title="El ID de la venta"),
    db: Session = Depends(get_db)
) -> DBVenta:
    """
    Dependencia para obtener una venta por ID con todas sus relaciones precargadas.
    Ahora carga la Persona asociada a la venta (ex-cliente).
    Lanza un error 404 si no se encuentra.
    """
    venta = db.query(DBVenta).options(
        # joinedload(DBVenta.cliente).joinedload(DBCliente.persona), # <-- ¡CAMBIO AQUÍ! Ahora es directamente .persona
        joinedload(DBVenta.persona), # Carga la Persona que realizó la compra
        joinedload(DBVenta.metodo_pago),
        joinedload(DBVenta.creador),
        joinedload(DBVenta.modificador),
        joinedload(DBVenta.detalles).joinedload(DBDetalleVenta.producto)
    ).filter(DBVenta.venta_id == venta_id).first()
    if venta is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Venta no encontrada.")
    return venta

@router_productos_public.get("/buscar_por_codigo/{codigo_producto}", response_model=ProductoSchemaBase)
def get_producto_by_codigo(
    codigo_producto: str = Path(..., description="Código único del producto"),
    db: Session = Depends(get_db)
):
    """
    Busca un producto por su código y devuelve su información básica.
    Util para puntos de venta para escanear productos.
    """
    db_producto = db.query(DBProducto).filter(
        DBProducto.codigo == codigo_producto,
        DBProducto.estado == EstadoEnum.activo
    ).first()
    if db_producto is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Producto no encontrado o inactivo.")
    return db_producto

@router.post("/", response_model=Venta, status_code=status.HTTP_201_CREATED)
def create_venta(
    venta_data: VentaCreate,
    db: Session = Depends(get_db),
    current_user: auth_utils.Usuario = Depends(auth_utils.get_current_active_user_with_role(ROLES_CAN_MANAGE_VENTAS))
):
    """
    Crea una nueva venta, valida stock y actualiza existencias de productos.
    """
    db.begin_nested() # Inicia una transacción anidada para atomicidad
    try:
        # Validar la persona asociada a la venta (ahora es persona_id, no cliente_id)
        if venta_data.persona_id: # Asegurarse de que el esquema VentaCreate use persona_id
            persona = db.query(DBPersona).filter(DBPersona.persona_id == venta_data.persona_id, DBPersona.estado == EstadoEnum.activo).first()
            if not persona:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Persona (cliente) con ID {venta_data.persona_id} no encontrada o inactiva.")
        else:
            # Si no se provee persona_id, se puede asumir una venta a "cliente genérico" o forzar que sea obligatoria
            # Depende de la lógica de negocio. Por ahora, permitiremos null como en tu original.
            pass

        # Validar el método de pago
        metodo_pago = db.query(DBMetodoPago).filter(DBMetodoPago.metodo_pago_id == venta_data.metodo_pago_id, DBMetodoPago.estado == EstadoEnum.activo).first()
        if not metodo_pago:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Método de pago con ID {venta_data.metodo_pago_id} no encontrado o inactivo.")
        
        # Validar que haya al menos un detalle de venta
        if not venta_data.detalles:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="La venta debe tener al menos un detalle de producto.")

        total_venta = Decimal(0)
        productos_a_actualizar = {} # Diccionario para almacenar productos y la cantidad a restar de su stock

        # Procesar cada detalle de la venta
        for detalle_data in venta_data.detalles:
            producto = db.query(DBProducto).filter(DBProducto.producto_id == detalle_data.producto_id, DBProducto.estado == EstadoEnum.activo).first()
            if not producto:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Producto con ID {detalle_data.producto_id} no encontrado o inactivo.")
            
            if detalle_data.cantidad <= 0:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"La cantidad para el producto ID {detalle_data.producto_id} debe ser un valor positivo.")
            
            # Verificar stock disponible
            if (producto.stock or 0) < detalle_data.cantidad:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Stock insuficiente para el producto '{producto.nombre}'. Stock actual: {producto.stock or 0}, Cantidad solicitada: {detalle_data.cantidad}.")
            
            # Calcular subtotal del detalle y sumarlo al total de la venta
            total_venta += Decimal(str(detalle_data.cantidad)) * Decimal(str(detalle_data.precio_unitario))
            
            # Almacenar producto y cantidad para la actualización de stock posterior
            productos_a_actualizar[producto.producto_id] = {"instancia": producto, "cantidad_a_restar": detalle_data.cantidad}

        # Crear la nueva instancia de Venta
        nueva_venta = DBVenta(
            # cliente_id=venta_data.cliente_id, # <-- ¡ELIMINADO!
            persona_id=venta_data.persona_id, # <-- ¡CAMBIO AQUÍ! Usar persona_id
            total=total_venta,
            metodo_pago_id=venta_data.metodo_pago_id,
            estado=venta_data.estado,
            creado_por=current_user.usuario_id,
            modificado_por=current_user.usuario_id,
            # Crear instancias de DetalleVenta directamente
            detalles=[DBDetalleVenta(**d.model_dump()) for d in venta_data.detalles]
        )
        db.add(nueva_venta)
        db.flush() # Para que nueva_venta.venta_id esté disponible si es necesario para detalles

        # Actualizar el stock de los productos
        for data in productos_a_actualizar.values():
            data["instancia"].stock -= data["cantidad_a_restar"]
            data["instancia"].modificado_por = current_user.usuario_id
            db.add(data["instancia"]) # Asegurarse de que los productos actualizados se pongan en la sesión

        db.commit() # Confirma todos los cambios de la transacción
        db.refresh(nueva_venta) # Refresca para cargar las relaciones y los detalles
        
        # Una vez creada, la recuperamos con todas sus relaciones cargadas para la respuesta
        return get_venta_or_404(nueva_venta.venta_id, db)

    except HTTPException:
        db.rollback() # Revierte la transacción si hay una HTTPException
        raise # Re-lanza la HTTPException
    except Exception as e:
        db.rollback() # Revierte la transacción si hay cualquier otra excepción
        # Log del error para depuración
        print(f"ERROR al crear la venta: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Ocurrió un error inesperado al crear la Venta: {str(e)}")


@router.get("/", response_model=List[Venta])
def read_ventas(
    estado: Optional[EstadoVentaEnum] = Query(None, description="Filtrar por estado de la venta"),
    persona_id: Optional[int] = Query(None, description="Filtrar por ID de la persona asociada a la venta"), # <-- ¡CAMBIO AQUÍ!
    metodo_pago_id: Optional[int] = Query(None, description="Filtrar por ID del método de pago"),
    fecha_desde: Optional[datetime] = Query(None, description="Fecha de inicio del rango de búsqueda (inclusive)"),
    fecha_hasta: Optional[datetime] = Query(None, description="Fecha de fin del rango de búsqueda (inclusive)"),
    search: Optional[str] = Query(None, description="Buscar por nombre/apellido de persona o nombre de producto"),
    skip: int = Query(0, ge=0), limit: int = Query(100, gt=0),
    db: Session = Depends(get_db),
    current_user: auth_utils.Usuario = Depends(auth_utils.get_current_active_user_with_role(ROLES_CAN_MANAGE_VENTAS))
):
    """
    Obtiene una lista de ventas con opciones de filtrado y búsqueda.
    """
    query = db.query(DBVenta).options(
        # joinedload(DBVenta.cliente).joinedload(DBCliente.persona), # <-- ¡ELIMINADO!
        joinedload(DBVenta.persona), # <-- ¡CAMBIO AQUÍ!
        joinedload(DBVenta.metodo_pago), joinedload(DBVenta.creador), joinedload(DBVenta.modificador),
        joinedload(DBVenta.detalles).joinedload(DBDetalleVenta.producto)
    )

    if estado: query = query.filter(DBVenta.estado == estado)
    if persona_id: query = query.filter(DBVenta.persona_id == persona_id) # <-- ¡CAMBIO AQUÍ!
    if metodo_pago_id: query = query.filter(DBVenta.metodo_pago_id == metodo_pago_id)
    if fecha_desde: query = query.filter(DBVenta.fecha_venta >= fecha_desde)
    if fecha_hasta: query = query.filter(DBVenta.fecha_venta <= fecha_hasta)
    
    if search:
        search_pattern = f"%{search}%"
        query = query.filter(or_(
            # Buscar en el nombre/apellido de la persona asociada a la venta
            DBVenta.persona.has(or_( # <-- ¡CAMBIO AQUÍ!
                DBPersona.nombre.ilike(search_pattern),
                DBPersona.apellido_paterno.ilike(search_pattern),
                DBPersona.apellido_materno.ilike(search_pattern) # <-- ¡MEJORA! Incluir apellido_materno
            )),
            # Buscar en los nombres de los productos en los detalles de la venta
            DBVenta.detalles.any(DBDetalleVenta.producto.has(DBProducto.nombre.ilike(search_pattern)))
        ))
    
    return query.order_by(DBVenta.venta_id.desc()).offset(skip).limit(limit).all()

@router.get("/{venta_id}", response_model=Venta)
def get_venta(
    venta: DBVenta = Depends(get_venta_or_404),
    current_user: auth_utils.Usuario = Depends(auth_utils.get_current_active_user_with_role(ROLES_CAN_MANAGE_VENTAS))
):
    """
    Obtiene los detalles de una venta específica por su ID.
    """
    return venta

@router.patch("/{venta_id}/anular", response_model=Venta)
def anular_venta(
    db_venta: DBVenta = Depends(get_venta_or_404),
    db: Session = Depends(get_db),
    current_user: auth_utils.Usuario = Depends(auth_utils.get_current_active_user_with_role(ROLES_CAN_MANAGE_VENTAS))
):
    """
    Anula una venta existente y repone el stock de los productos involucrados.
    """
    if db_venta.estado == EstadoVentaEnum.anulada:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="La venta ya está anulada.")
    
    db.begin_nested() # Inicia una transacción anidada
    try:
        # Reponer el stock de los productos
        for detalle in db_venta.detalles:
            if detalle.producto: # Asegurarse de que el producto esté cargado
                detalle.producto.stock = (detalle.producto.stock or 0) + detalle.cantidad
                detalle.producto.modificado_por = current_user.usuario_id
                db.add(detalle.producto) # Añadir el producto actualizado a la sesión

        db_venta.estado = EstadoVentaEnum.anulada
        db_venta.modificado_por = current_user.usuario_id
        db.add(db_venta) # Asegurarse de que la venta actualizada se ponga en la sesión

        db.commit() # Confirma todos los cambios
        db.refresh(db_venta) # Refresca para cargar el estado y los productos actualizados
        return db_venta
    except Exception as e:
        db.rollback() # Revierte la transacción
        print(f"ERROR al anular la venta: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Ocurrió un error al anular la venta: {str(e)}")