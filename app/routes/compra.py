# backEnd/app/routes/compra.py

from typing import List, Optional, Union
from datetime import datetime, timezone 
from decimal import Decimal
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import or_, and_
import os
import logging
from twilio.rest import Client
from twilio.base.exceptions import TwilioRestException 
from .. import auth as auth_utils
from ..database import get_db
from ..models.compra import Compra as DBCompra
from ..models.detalle_compra import DetalleCompra as DBDetalleCompra
from ..models.producto import Producto as DBProducto 
from ..models.proveedor import Proveedor as DBProveedor 
from ..models.usuario import Usuario as DBUsuario 
from ..models.persona import Persona as DBPersona
from ..models.empresa import Empresa as DBEmpresa
from ..models.enums import EstadoCompraEnum , EstadoEnum



from ..schemas.compra import (
    Compra, 
    CompraCreate, 
    CompraUpdate, 
    DetalleCompraCreate, 
    DetalleCompra,
    CompraPagination # Importar el nuevo esquema de paginación
)

logger = logging.getLogger(__name__)
account_sid = os.environ.get('TWILIO_ACCOUNT_SID')
auth_token = os.environ.get('TWILIO_AUTH_TOKEN')
twilio_phone_number_sms = os.environ.get('TWILIO_PHONE_NUMBER') 
twilio_whatsapp_from = os.environ.get('TWILIO_WHATSAPP_FROM') # Número de Twilio/Sandbox para WhatsApp (ej. "whatsapp:+1415238886")


twilio_client = None
if account_sid and auth_token:
    try:
        twilio_client = Client(account_sid, auth_token)
        logger.info("Cliente de Twilio inicializado correctamente.")
    except Exception as e:
        logger.error(f"Error al inicializar cliente de Twilio: {e}")
        twilio_client = None 
else:
    logger.warning("Variables de entorno TWILIO_ACCOUNT_SID o TWILIO_AUTH_TOKEN no configuradas. El envío de mensajes estará deshabilitado.")





router = APIRouter(
    prefix="/compras",
    tags=["compras"]
)

ROLES_CAN_MANAGE_COMPRAS = ["Administrador", "Empleado", ]


# --- Función Utilitaria para Notificar al Proveedor (Simulación o Twilio) ---
def notify_proveedor(db: Session, compra_id: int, proveedor_id: int, total: Decimal):
    """
    Intenta notificar al proveedor sobre una nueva compra.
    Usa Twilio (WhatsApp) si está configurado, de lo contrario, registra en los logs.
    Incluye detalles de la compra en el mensaje.
    """
    # Obtener información completa de la compra, incluyendo proveedor y detalles con productos
    db_compra = db.query(DBCompra).options(
        joinedload(DBCompra.proveedor).joinedload(DBProveedor.persona), # Carga proveedor y su persona/empresa
        joinedload(DBCompra.proveedor).joinedload(DBProveedor.empresa),
        joinedload(DBCompra.detalles).joinedload(DBDetalleCompra.producto) # Carga los detalles y sus productos
    ).filter(DBCompra.compra_id == compra_id).first()

    if not db_compra:
        logger.error(f"No se encontró la compra con ID {compra_id} para notificar al proveedor.")
        return # Salir si la compra no existe

    proveedor = db_compra.proveedor # Obtener el objeto proveedor cargado
    telefono_proveedor = None
    nombre_proveedor = "Proveedor Desconocido"

    if proveedor:
        if proveedor.persona:
            telefono_proveedor = proveedor.persona.telefono
            nombre_proveedor = f"{proveedor.persona.nombre} {proveedor.persona.apellido_paterno or ''}".strip()
        elif proveedor.empresa:
            telefono_proveedor = proveedor.empresa.telefono
            nombre_proveedor = proveedor.empresa.razon_social

    # Construir el mensaje detallado
    mensaje = f"Estimado(a) {nombre_proveedor},\n\n"
    mensaje += f"Se ha registrado una nueva orden de compra con ID #{db_compra.compra_id}.\n"
    mensaje += f"Fecha: {db_compra.fecha_compra.strftime('%Y-%m-%d %H:%M')}\n" # Formatea la fecha/hora
    mensaje += f"Total: {db_compra.total:.2f}\n\n"

    if db_compra.detalles:
        mensaje += "Detalles de la compra:\n"
        for i, detalle in enumerate(db_compra.detalles):
            # Asegúrate de que el producto está cargado y tiene nombre
            producto_nombre = detalle.producto.nombre if detalle.producto else "Producto Desconocido"
            mensaje += f"{i+1}. {producto_nombre} - Cantidad: {detalle.cantidad} - Precio Unitario: {detalle.precio_unitario:.2f}\n"
    else:
        mensaje += "Esta compra no tiene detalles de productos.\n"

    mensaje += "\nPor favor, contactar para coordinar la entrega."

    if telefono_proveedor and twilio_client and twilio_whatsapp_from:

        telefono_destino_whatsapp = f"whatsapp:{telefono_proveedor}"

        try:
            message = twilio_client.messages.create(
                body=mensaje,
                from_=twilio_whatsapp_from, 
                to=telefono_destino_whatsapp
            )
            logger.info(f"Mensaje de Twilio WhatsApp enviado a {telefono_destino_whatsapp} (Proveedor: {nombre_proveedor}). SID: {message.sid}")
        except TwilioRestException as e:
            logger.error(f"Error al enviar mensaje de Twilio WhatsApp a {telefono_destino_whatsapp} (Proveedor: {nombre_proveedor}): {e}")
        except Exception as e:
            logger.error(f"Error inesperado al intentar enviar mensaje de Twilio WhatsApp a {telefono_destino_whatsapp} (Proveedor: {nombre_proveedor}): {e}")
    elif telefono_proveedor: # Si hay número pero Twilio WhatsApp no está configurado
        logger.info(f"SIMULACIÓN ENVÍO MENSAJE: A={telefono_proveedor} (Proveedor: {nombre_proveedor}), Mensaje:\n{mensaje}") # Imprime el mensaje completo en la simulación
    # --- FIN SIMULACIÓN ---
    else:
        logger.warning(f"No se pudo enviar mensaje al proveedor {nombre_proveedor} (ID: {proveedor_id}): Teléfono no disponible.")



@router.post("/", response_model=Compra, status_code=status.HTTP_201_CREATED)
def create_compra(
    compra_data: CompraCreate,
    db: Session = Depends(get_db),
    current_user: auth_utils.Usuario = Depends(auth_utils.require_menu_access("/compras")) # Verificar acceso al menú de categorías
):
    """
    Crea una nueva Compra con sus detalles, actualiza el stock de productos
    y opcionalmente notifica al proveedor por WhatsApp (si Twilio está configurado).
    Solo accesible por usuarios con permisos de gestión de compras.
    """
    db.begin_nested() 

    try:
      
        db_proveedor = db.query(DBProveedor).filter(
            DBProveedor.proveedor_id == compra_data.proveedor_id,
            DBProveedor.estado == EstadoEnum.activo
        ).first()
        if db_proveedor is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Proveedor con ID {compra_data.proveedor_id} no encontrado o inactivo.")

        if not compra_data.detalles:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="La compra debe tener al menos un detalle.")

        total_compra = Decimal(0)
        db_detalles = []
        
        # Recopilar todos los IDs de producto únicos de los detalles entrantes
        product_ids_in_details = {detalle.producto_id for detalle in compra_data.detalles}
        
        # Obtener todos los productos necesarios en una sola consulta
        # Usar un diccionario para una búsqueda eficiente
        products_map = {
            p.producto_id: p for p in db.query(DBProducto).filter(
                DBProducto.producto_id.in_(product_ids_in_details),
                DBProducto.estado == EstadoEnum.activo
            ).all()
        }

        for detalle_data in compra_data.detalles:
            db_producto = products_map.get(detalle_data.producto_id)
            if db_producto is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Producto con ID {detalle_data.producto_id} en el detalle no encontrado o inactivo.")

            if detalle_data.cantidad <= 0:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"La cantidad para el producto ID {detalle_data.producto_id} debe ser positiva.")

            precio_unitario_final = detalle_data.precio_unitario
            if precio_unitario_final is None or precio_unitario_final == Decimal(0):
                if db_producto.precio_compra is not None:
                    precio_unitario_final = db_producto.precio_compra
                else:
                    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"El producto '{db_producto.nombre}' (ID: {db_producto.producto_id}) no tiene un precio de compra definido y no se proporcionó un precio unitario para el detalle.")
            
            if precio_unitario_final < 0:
                 raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"El precio unitario final para el producto ID {detalle_data.producto_id} no puede ser negativo.")

            subtotal_detalle = detalle_data.cantidad * precio_unitario_final
            total_compra += subtotal_detalle

            db_detalle = DBDetalleCompra(
                producto_id=detalle_data.producto_id,
                cantidad=detalle_data.cantidad,
                precio_unitario=precio_unitario_final 
            )
            db_detalles.append(db_detalle)
            
            # Actualizar el stock directamente en el objeto de producto obtenido
            db_producto.stock = (db_producto.stock or 0) + detalle_data.cantidad
            db.add(db_producto) # Marcar como modificado para la actualización

        nueva_compra = DBCompra(
            proveedor_id=compra_data.proveedor_id,
            fecha_compra=compra_data.fecha_compra or datetime.now(timezone.utc), # Asigna fecha actual si no se proporciona
            total=total_compra,
            estado=compra_data.estado,
            creado_por=current_user.usuario_id,
            modificado_por=None
        )

        nueva_compra.detalles.extend(db_detalles)

        db.add(nueva_compra)
        db.flush() # Usar flush para obtener nueva_compra.compra_id antes del commit

        db.commit()
        db.refresh(nueva_compra, attribute_names=['proveedor', 'creador', 'modificador', 'detalles']) # Refrescar con relaciones

        try:
            notify_proveedor(db, nueva_compra.compra_id, nueva_compra.proveedor_id, nueva_compra.total)
        except Exception as e:
            logger.error(f"Error al intentar notificar al proveedor para compra {nueva_compra.compra_id}: {e}")

        return nueva_compra # Return the refreshed object

    except HTTPException as e:
        db.rollback() # Revertir todos los cambios en caso de HTTPException
        raise e
    except Exception as e:
        db.rollback() # Revertir todos los cambios en caso de cualquier otro error
        
        logger.error(f"Error inesperado durante la creación de Compra: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Ocurrió un error al crear la Compra.")


# --- Endpoint para Listar Compras ---
@router.get("/", response_model=CompraPagination)
def read_compras(
    # Parámetros de filtro y paginación
    estado: Optional[EstadoCompraEnum] = Query(None, description="Filtrar por estado de la compra"),
    proveedor_id: Optional[int] = Query(None, description="Filtrar por ID de proveedor"),
    creador_id: Optional[int] = Query(None, description="Filtrar por ID de usuario que creó la compra"),
    fecha_desde: Optional[datetime] = Query(None, description="Filtrar compras desde esta fecha (YYYY-MM-DD)"),
    fecha_hasta: Optional[datetime] = Query(None, description="Filtrar compras hasta esta fecha (YYYY-MM-DD)"),
    search: Optional[str] = Query(None, description="Texto de búsqueda por nombre de proveedor o nombre de producto"),
    skip: int = Query(0, ge=0, description="Número de elementos a omitir (paginación)"),
    limit: int = Query(100, gt=0, description="Número máximo de elementos a retornar (paginación)"),
    db: Session = Depends(get_db),
    current_user: auth_utils.Usuario = Depends(auth_utils.require_menu_access("/compras")) # Verificar acceso al menú de categorías
):
    """
    Obtiene una lista de Compras con opciones de filtro, búsqueda y paginación.
    Incluye el proveedor, creador, modificador y detalles de compra anidados.
    Accesible solo por usuarios con permisos de gestión de compras.
    """
    query = db.query(DBCompra).options(
        joinedload(DBCompra.proveedor).joinedload(DBProveedor.persona), # Carga la persona del proveedor
        joinedload(DBCompra.proveedor).joinedload(DBProveedor.empresa),  # Carga la empresa del proveedor
        joinedload(DBCompra.creador),
        joinedload(DBCompra.modificador),
        joinedload(DBCompra.detalles).joinedload(DBDetalleCompra.producto) # Carga los productos en los detalles
    )

    # Aplicar filtros
    if estado:
        query = query.filter(DBCompra.estado == estado)
    if proveedor_id:
        query = query.filter(DBCompra.proveedor_id == proveedor_id)
    if creador_id:
        query = query.filter(DBCompra.creado_por == creador_id)
    if fecha_desde:
        query = query.filter(DBCompra.fecha_compra >= fecha_desde)
    if fecha_hasta:
        query = query.filter(DBCompra.fecha_compra <= fecha_hasta)

    # Aplicar búsqueda combinada por nombre de proveedor o nombre de producto
    if search:
        search_pattern = f"%{search}%"
        query = query.filter(
            or_(
                # Búsqueda en nombre/razón social del proveedor
                DBCompra.proveedor.has(
                    or_(
                        DBProveedor.persona.has(
                            or_(
                                DBPersona.nombre.ilike(search_pattern),
                                DBPersona.apellido_paterno.ilike(search_pattern),
                                DBPersona.apellido_materno.ilike(search_pattern)
                            )
                        ),
                        DBProveedor.empresa.has(
                            DBEmpresa.razon_social.ilike(search_pattern)
                        )
                    )
                ),
                # Búsqueda en nombres de productos dentro de los detalles de la compra
                DBCompra.detalles.any(
                    DBDetalleCompra.producto.has(
                        DBProducto.nombre.ilike(search_pattern)
                    )
                )
            )
        )

    total = query.count() # Contar el total de compras antes de aplicar skip/limit
    compras = query.offset(skip).limit(limit).all()

    return {"items": compras, "total": total} # Devolver el objeto de paginación
# --- Endpoint para Obtener una Compra por ID ---
@router.get("/{compra_id}", response_model=Compra) # Retorna el esquema Compra
def read_compra(
    compra_id: int,
    db: Session = Depends(get_db),
    current_user: auth_utils.Usuario = Depends(auth_utils.require_menu_access("/compras")) # Verificar acceso al menú de categorías
):
    """
    Obtiene la información de una Compra específica por su ID.
    Incluye proveedor, usuario, creador, modificador y detalles con productos.
    Accesible solo por usuarios con permisos de gestión de compras (por defecto).
    """
    # Obtener la compra por ID cargando todas las relaciones necesarias
    compra = db.query(DBCompra).options(
        joinedload(DBCompra.proveedor).joinedload(DBProveedor.persona),
        joinedload(DBCompra.proveedor).joinedload(DBProveedor.empresa),
        joinedload(DBCompra.creador),
        joinedload(DBCompra.modificador),
        joinedload(DBCompra.detalles).joinedload(DBDetalleCompra.producto)
    ).filter(DBCompra.compra_id == compra_id).first()

    if compra is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Compra no encontrada")

    return compra # Retorna el objeto DBCompra que FastAPI serializa a Compra


# --- Endpoint para Actualizar una Compra (PUT /compras/{compra_id}) ---
@router.put("/{compra_id}", response_model=Compra)
def update_compra(
    compra_id: int,
    compra_update: CompraUpdate,
    db: Session = Depends(get_db),
    current_user: auth_utils.Usuario = Depends(auth_utils.require_menu_access("/compras")) # Verificar acceso al menú de categorías
):

    db.begin_nested() 

    try:
        db_compra = db.query(DBCompra).options(
            joinedload(DBCompra.proveedor).joinedload(DBProveedor.persona),
            joinedload(DBCompra.proveedor).joinedload(DBProveedor.empresa),
            joinedload(DBCompra.creador),
            joinedload(DBCompra.modificador),
            joinedload(DBCompra.detalles).joinedload(DBDetalleCompra.producto) # Cargar los detalles y sus productos
        ).filter(DBCompra.compra_id == compra_id).first()

        if db_compra is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Compra no encontrada.")

        if db_compra.estado in [EstadoCompraEnum.completada, EstadoCompraEnum.anulada]:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"No se puede modificar una compra en estado '{db_compra.estado.value}'.")

        update_data_compra = compra_update.model_dump(exclude_unset=True, exclude={'detalles'})

        if 'proveedor_id' in update_data_compra and update_data_compra['proveedor_id'] != db_compra.proveedor_id:
            db_new_proveedor = db.query(DBProveedor).filter(
                DBProveedor.proveedor_id == update_data_compra['proveedor_id'],
                DBProveedor.estado == EstadoEnum.activo
            ).first()
            if not db_new_proveedor:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Nuevo proveedor no encontrado o inactivo.")
            db_compra.proveedor_id = update_data_compra['proveedor_id']

        if 'fecha_compra' in update_data_compra:
            db_compra.fecha_compra = update_data_compra['fecha_compra']

        if 'estado' in update_data_compra and update_data_compra['estado'] != db_compra.estado:
            db_compra.estado = update_data_compra['estado']

        if compra_update.detalles is not None:
            productos_stock_change = {}

            # Calculate stock changes from existing details (revert)
            for db_detalle in db_compra.detalles:
                productos_stock_change[db_detalle.producto_id] = productos_stock_change.get(db_detalle.producto_id, 0) - db_detalle.cantidad

            # Delete old details
            for db_detalle in list(db_compra.detalles):
                db.delete(db_detalle)
            db.flush()

            new_db_detalles = []
            
            # Collect all unique product IDs from incoming details
            incoming_product_ids = {d.producto_id for d in compra_update.detalles}
            
            # Fetch all products for incoming details in one query
            incoming_products_map = {
                p.producto_id: p for p in db.query(DBProducto).filter(
                    DBProducto.producto_id.in_(incoming_product_ids),
                    DBProducto.estado == EstadoEnum.activo
                ).all()
            }

            for incoming_detalle_data in compra_update.detalles:
                db_producto = incoming_products_map.get(incoming_detalle_data.producto_id)
                if db_producto is None:
                    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Producto con ID {incoming_detalle_data.producto_id} en el detalle no encontrado o inactivo.")

                if incoming_detalle_data.cantidad <= 0:
                    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"La cantidad para el producto ID {incoming_detalle_data.producto_id} debe ser positiva.")

                precio_unitario_final = incoming_detalle_data.precio_unitario
                if precio_unitario_final is None or precio_unitario_final == Decimal(0):
                    if db_producto.precio_compra is not None:
                        precio_unitario_final = db_producto.precio_compra
                    else:
                        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"El producto '{db_producto.nombre}' (ID: {db_producto.producto_id}) no tiene un precio de compra definido y no se proporcionó un precio unitario para el detalle.")
                
                if precio_unitario_final < 0:
                    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"El precio unitario final para el producto ID {incoming_detalle_data.producto_id} no puede ser negativo.")

                new_db_detalle = DBDetalleCompra(
                    producto_id=incoming_detalle_data.producto_id,
                    cantidad=incoming_detalle_data.cantidad,
                    precio_unitario=precio_unitario_final 
                )
                new_db_detalles.append(new_db_detalle)
                
                productos_stock_change[incoming_detalle_data.producto_id] = productos_stock_change.get(incoming_detalle_data.producto_id, 0) + incoming_detalle_data.cantidad

            db_compra.detalles.extend(new_db_detalles)
            db.flush()
            
            # Aplicar los cambios de stock consolidados
            for producto_id, change in productos_stock_change.items():
                db_producto = incoming_products_map.get(producto_id) # Use the map for lookup
                if db_producto:
                    db_producto.stock = (db_producto.stock or 0) + change
                    db.add(db_producto)
                else:
                    logger.warning(f"Producto con ID {producto_id} no encontrado al intentar ajustar stock para la compra {compra_id}.")

            db.flush()
            new_total = Decimal(0)
            db.refresh(db_compra, attribute_names=['detalles'])
            for detalle in db_compra.detalles:
                new_total += Decimal(str(detalle.cantidad)) * Decimal(str(detalle.precio_unitario))
            db_compra.total = new_total

        db_compra.modificado_por = current_user.usuario_id

        db.commit() 
        db.refresh(db_compra) 

        db_compra_for_response = db.query(DBCompra).options(
            joinedload(DBCompra.proveedor).joinedload(DBProveedor.persona),
            joinedload(DBCompra.proveedor).joinedload(DBProveedor.empresa),
            joinedload(DBCompra.creador),
            joinedload(DBCompra.modificador),
            joinedload(DBCompra.detalles).joinedload(DBDetalleCompra.producto)
        ).filter(DBCompra.compra_id == db_compra.compra_id).first()

        return db_compra_for_response

    except HTTPException as e:
        db.rollback() # Revertir todos los cambios en caso de HTTPException
        raise e
    except Exception as e:
        db.rollback() # Revertir todos los cambios en caso de cualquier otro error
         
        logger.error(f"Error inesperado durante la creación de Compra: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Ocurrió un error al crear la Compra.")

@router.patch("/{compra_id}/anular", response_model=Compra)
def anular_compra(
    compra_id: int,
    db: Session = Depends(get_db),
    current_user: auth_utils.Usuario = Depends(auth_utils.require_menu_access("/compras")) # Verificar acceso al menú de categorías
):
    """
    Anula una Compra por su ID y revierte el stock de los productos asociados.
    Solo accesible por usuarios con permisos de gestión de compras.
    """
    db_compra = db.query(DBCompra).options(
        joinedload(DBCompra.proveedor).joinedload(DBProveedor.persona),
        joinedload(DBCompra.proveedor).joinedload(DBProveedor.empresa),
        joinedload(DBCompra.creador),
        joinedload(DBCompra.modificador),
        joinedload(DBCompra.detalles).joinedload(DBDetalleCompra.producto)
    ).filter(DBCompra.compra_id == compra_id).first()

    if db_compra is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Compra no encontrada.")

    if db_compra.estado == EstadoCompraEnum.anulada:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="La compra ya está anulada.")

    try:
        db.begin_nested() 

        # Collect all unique product IDs from the details
        product_ids_in_details = {detalle.producto_id for detalle in db_compra.detalles}
        
        # Fetch all necessary products in a single query
        products_map = {
            p.producto_id: p for p in db.query(DBProducto).filter(
                DBProducto.producto_id.in_(product_ids_in_details)
            ).all()
        }

        for detalle in db_compra.detalles:
            db_producto = products_map.get(detalle.producto_id)
            if db_producto:
                if (db_producto.stock or 0) < detalle.cantidad:
                     logger.warning(f"Intentando revertir stock para Producto ID {detalle.producto_id} (Compra {compra_id}), pero el stock actual ({db_producto.stock or 0}) es menor que la cantidad a restar ({detalle.cantidad}). Esto podría llevar a stock negativo.")

                db_producto.stock = (db_producto.stock or 0) - detalle.cantidad
                db.add(db_producto) 

        db_compra.estado = EstadoCompraEnum.anulada
        db_compra.modificado_por = current_user.usuario_id 

        db.commit()
        db.refresh(db_compra, attribute_names=['proveedor', 'creador', 'modificador', 'detalles']) # Refresh with relations

        return db_compra 

    except HTTPException as e:
        db.rollback()
        raise e
    except Exception as e:
        db.rollback()
        logger.error(f"Error al anular compra {compra_id} y revertir stock: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Ocurrió un error al anular la compra y revertir el stock.")


@router.patch("/{compra_id}/completar", response_model=Compra)
def completar_compra(
    compra_id: int,
    db: Session = Depends(get_db),
    current_user: auth_utils.Usuario = Depends(auth_utils.require_menu_access("/compras")) # Verificar acceso al menú de categorías
):
    """
    Marca una Compra como 'completada' por su ID y actualiza el stock de los productos asociados.
    Solo accesible por usuarios con permisos de gestión de compras.
    """
    db_compra = db.query(DBCompra).options(
        joinedload(DBCompra.proveedor).joinedload(DBProveedor.persona),
        joinedload(DBCompra.proveedor).joinedload(DBProveedor.empresa),
        joinedload(DBCompra.creador),
        joinedload(DBCompra.modificador),
        joinedload(DBCompra.detalles).joinedload(DBDetalleCompra.producto)
    ).filter(DBCompra.compra_id == compra_id).first()

    if db_compra is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Compra no encontrada.")

    if db_compra.estado == EstadoCompraEnum.completada:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="La compra ya está completada.")
    if db_compra.estado == EstadoCompraEnum.anulada:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No se puede completar una compra anulada.")

    try:
        db.begin_nested()

        # Collect all unique product IDs from the details
        product_ids_in_details = {detalle.producto_id for detalle in db_compra.detalles}
        
        # Fetch all necessary products in a single query
        products_map = {
            p.producto_id: p for p in db.query(DBProducto).filter(
                DBProducto.producto_id.in_(product_ids_in_details)
            ).all()
        }

        for detalle in db_compra.detalles:
            db_producto = products_map.get(detalle.producto_id)
            if db_producto:
                db_producto.stock = (db_producto.stock or 0) + detalle.cantidad 
                db_producto.modificado_por = current_user.usuario_id
                db.add(db_producto)

        db_compra.estado = EstadoCompraEnum.completada
        db_compra.modificado_por = current_user.usuario_id 

        db.commit() 
        db.refresh(db_compra, attribute_names=['proveedor', 'creador', 'modificador', 'detalles']) # Refrescar con relaciones

        return db_compra

    except HTTPException as e:
        db.rollback()
        raise e
    except Exception as e:
        db.rollback()
        logger.error(f"Error al completar compra {compra_id} y actualizar stock: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Ocurrió un error al completar la compra y actualizar el stock.")