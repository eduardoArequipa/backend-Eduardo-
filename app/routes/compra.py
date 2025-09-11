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
from ..models.conversion import Conversion as DBConversion
# Importar el servicio de precios
from ..services.precio_service import PrecioService


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
    current_user: auth_utils.Usuario = Depends(auth_utils.require_menu_access("/compras"))
):
    """
    Crea una nueva Compra con sus detalles. El stock NO se modifica hasta que la compra se marca como 'completada'.
    """
    db.begin_nested() 

    try:
        db_proveedor = db.query(DBProveedor).filter(
            DBProveedor.proveedor_id == compra_data.proveedor_id,
            DBProveedor.estado == EstadoEnum.activo
        ).first()
        if not db_proveedor:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Proveedor con ID {compra_data.proveedor_id} no encontrado o inactivo.")

        if not compra_data.detalles:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="La compra debe tener al menos un detalle.")

        total_compra = Decimal(0)
        db_detalles = []
        
        product_ids = {detalle.producto_id for detalle in compra_data.detalles}
        products_map = {p.producto_id: p for p in db.query(DBProducto).filter(DBProducto.producto_id.in_(product_ids)).options(joinedload(DBProducto.conversiones)).all()}

        for detalle_data in compra_data.detalles:
            db_producto = products_map.get(detalle_data.producto_id)
            if not db_producto or db_producto.estado != EstadoEnum.activo:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Producto con ID {detalle_data.producto_id} no encontrado o inactivo.")

            if detalle_data.cantidad <= 0:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"La cantidad para el producto ID {detalle_data.producto_id} debe ser positiva.")

            # Validar presentación si existe
            if detalle_data.presentacion_compra:
                conversion = next((c for c in db_producto.conversiones if c.nombre_presentacion == detalle_data.presentacion_compra and c.es_para_compra), None)
                if not conversion:
                    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"La presentación de compra '{detalle_data.presentacion_compra}' no es válida o no está habilitada para compras en el producto '{db_producto.nombre}'.")

            precio_unitario_final = detalle_data.precio_unitario
            if precio_unitario_final is None or precio_unitario_final == Decimal(0):
                if db_producto.precio_compra is not None:
                    precio_unitario_final = db_producto.precio_compra
                else:
                    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"El producto '{db_producto.nombre}' (ID: {db_producto.producto_id}) no tiene un precio de compra definido.")
            
            if precio_unitario_final < 0:
                 raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"El precio unitario final para el producto ID {detalle_data.producto_id} no puede ser negativo.")

            subtotal_detalle = detalle_data.cantidad * precio_unitario_final
            total_compra += subtotal_detalle

            db_detalle = DBDetalleCompra(
                producto_id=detalle_data.producto_id,
                cantidad=detalle_data.cantidad,
                precio_unitario=precio_unitario_final,
                presentacion_compra=detalle_data.presentacion_compra
            )
            db_detalles.append(db_detalle)

        nueva_compra = DBCompra(
            proveedor_id=compra_data.proveedor_id,
            fecha_compra=compra_data.fecha_compra or datetime.now(timezone.utc),
            total=total_compra,
            estado=compra_data.estado or EstadoCompraEnum.pendiente,
            creado_por=current_user.usuario_id
        )

        nueva_compra.detalles.extend(db_detalles)
        db.add(nueva_compra)
        db.commit()
        db.refresh(nueva_compra)

        try:
            notify_proveedor(db, nueva_compra.compra_id, nueva_compra.proveedor_id, nueva_compra.total)
        except Exception as e:
            logger.error(f"Error al notificar al proveedor: {e}")

        return nueva_compra

    except HTTPException as e:
        db.rollback()
        raise e
    except Exception as e:
        db.rollback()
        logger.error(f"Error inesperado al crear Compra: {e}", exc_info=True)
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
    current_user: auth_utils.Usuario = Depends(auth_utils.require_menu_access("/compras"))
):
    """
    Actualiza una compra que está en estado 'pendiente'. 
    No modifica el stock, solo los detalles de la orden de compra.
    """
    db.begin_nested() 

    try:
        db_compra = db.query(DBCompra).options(
            joinedload(DBCompra.detalles).joinedload(DBDetalleCompra.producto)
        ).filter(DBCompra.compra_id == compra_id).first()

        if db_compra is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Compra no encontrada.")

        if db_compra.estado != EstadoCompraEnum.pendiente:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Solo se pueden modificar compras en estado 'pendiente'. Estado actual: '{db_compra.estado.value}'.")

        update_data = compra_update.model_dump(exclude_unset=True, exclude={'detalles'})

        # Actualizar campos de la compra principal
        for key, value in update_data.items():
            setattr(db_compra, key, value)

        # Actualizar detalles si se proporcionan
        if compra_update.detalles is not None:
            # Eliminar detalles antiguos
            for detalle in db_compra.detalles:
                db.delete(detalle)
            db.flush()

            # Crear nuevos detalles y recalcular el total
            new_total = Decimal(0)
            new_detalles = []
            
            product_ids = {d.producto_id for d in compra_update.detalles}
            products_map = {p.producto_id: p for p in db.query(DBProducto).filter(DBProducto.producto_id.in_(product_ids)).options(joinedload(DBProducto.conversiones)).all()}

            for detalle_data in compra_update.detalles:
                db_producto = products_map.get(detalle_data.producto_id)
                if not db_producto or db_producto.estado != EstadoEnum.activo:
                    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Producto con ID {detalle_data.producto_id} no encontrado o inactivo.")
                
                if detalle_data.cantidad <= 0:
                    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="La cantidad debe ser positiva.")

                # Validar presentación
                if detalle_data.presentacion_compra:
                    conversion = next((c for c in db_producto.conversiones if c.nombre_presentacion == detalle_data.presentacion_compra and c.es_para_compra), None)
                    if not conversion:
                        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Presentación '{detalle_data.presentacion_compra}' no válida o no está habilitada para compras en '{db_producto.nombre}'.")

                precio_unitario = detalle_data.precio_unitario
                if precio_unitario is None or precio_unitario == Decimal(0):
                    if db_producto.precio_compra is not None:
                        precio_unitario = db_producto.precio_compra
                    else:
                        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"El producto '{db_producto.nombre}' no tiene un precio de compra definido.")

                new_total += detalle_data.cantidad * precio_unitario
                new_detalles.append(DBDetalleCompra(**detalle_data.model_dump()))

            db_compra.detalles = new_detalles
            db_compra.total = new_total

        db_compra.modificado_por = current_user.usuario_id
        db.commit()
        db.refresh(db_compra)
        return db_compra

    except HTTPException as e:
        db.rollback()
        raise e
    except Exception as e:
        db.rollback()
        logger.error(f"Error inesperado al actualizar Compra: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Ocurrió un error al actualizar la Compra.")

@router.patch("/{compra_id}/anular", response_model=Compra)
def anular_compra(
    compra_id: int,
    db: Session = Depends(get_db),
    current_user: auth_utils.Usuario = Depends(auth_utils.require_menu_access("/compras"))
):
    """
    Anula una Compra por su ID. Esta acción es solo un cambio de estado y no revierte el stock,
    asumiendo que el stock solo se añade al completar la compra.
    """
    db_compra = db.query(DBCompra).filter(DBCompra.compra_id == compra_id).first()

    if db_compra is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Compra no encontrada.")

    if db_compra.estado == EstadoCompraEnum.anulada:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="La compra ya está anulada.")

    if db_compra.estado == EstadoCompraEnum.completada:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No se puede anular una compra que ya fue completada. Se debe gestionar una devolución.")

    try:
        db.begin_nested() 

        db_compra.estado = EstadoCompraEnum.anulada
        db_compra.modificado_por = current_user.usuario_id 

        db.commit()
        db.refresh(db_compra)

        return db_compra 

    except HTTPException as e:
        db.rollback()
        raise e
    except Exception as e:
        db.rollback()
        logger.error(f"Error al anular compra {compra_id}: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Ocurrió un error al anular la compra.")


@router.patch("/{compra_id}/completar", response_model=Compra)
def completar_compra(
    compra_id: int,
    db: Session = Depends(get_db),
    current_user: auth_utils.Usuario = Depends(auth_utils.require_menu_access("/compras"))
):
    """
    Marca una Compra como 'completada', actualiza el stock y el precio de compra
    de los productos asociados, utilizando la lógica de conversión de unidades.
    """
    db_compra = db.query(DBCompra).options(
        joinedload(DBCompra.detalles).joinedload(DBDetalleCompra.producto).joinedload(DBProducto.conversiones)
    ).filter(DBCompra.compra_id == compra_id).first()

    if db_compra is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Compra no encontrada.")

    if db_compra.estado == EstadoCompraEnum.completada:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="La compra ya está completada.")
    if db_compra.estado == EstadoCompraEnum.anulada:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No se puede completar una compra anulada.")

    try:
        db.begin_nested()

        for detalle in db_compra.detalles:
            db_producto = detalle.producto
            if not db_producto:
                continue

            conversion_factor = Decimal(1)
            # El precio guardado en el detalle es el costo de la presentación (ej: precio de la caja)
            precio_presentacion = Decimal(str(detalle.precio_unitario))

            if detalle.presentacion_compra and detalle.presentacion_compra != 'Unidad':
                presentacion_nombre = detalle.presentacion_compra.strip()
                # Ahora busca una conversión que sea válida para compras
                conversion = next((c for c in db_producto.conversiones if c.nombre_presentacion.lower() == presentacion_nombre.lower() and c.es_para_compra), None)
                
                if conversion:
                    # Asegurarse de que el factor de conversión no sea cero
                    if conversion.unidades_por_presentacion > 0:
                        conversion_factor = Decimal(conversion.unidades_por_presentacion)
                    else:
                         raise HTTPException(
                            status_code=status.HTTP_400_BAD_REQUEST,
                            detail=f"El factor de conversión para la presentación '{detalle.presentacion_compra}' del producto '{db_producto.nombre}' es cero."
                        )
                else:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"La presentación '{detalle.presentacion_compra}' no es válida o no está habilitada para compras en el producto '{db_producto.nombre}'."
                    )
            
            # --- INICIO DE LA NUEVA LÓGICA ---

            # 1. Calcular el nuevo costo por unidad base
            nuevo_precio_compra_unitario = precio_presentacion / conversion_factor

            # 2. Calcular la cantidad total de unidades base a añadir al stock
            stock_to_add = Decimal(detalle.cantidad) * conversion_factor
            
            # 3. Actualizar el stock del producto (Corregido a 'stock')
            db_producto.stock = (db_producto.stock or Decimal(0)) + stock_to_add

            # --- FIN DE LA NUEVA LÓGICA ---

            db.add(db_producto)

        # Cambiar estado de compra a completada
        db_compra.estado = EstadoCompraEnum.completada
        db_compra.modificado_por = current_user.usuario_id 

        # Hacer commit de los cambios de stock primero
        db.commit()
        
        # Ahora actualizar precios usando el servicio (que recalcula promedio ponderado)
        PrecioService.actualizar_precios_por_compra(db, compra_id)
        
        db.refresh(db_compra)

        return db_compra

    except HTTPException as e:
        db.rollback()
        raise e
    except Exception as e:
        db.rollback()
        logger.error(f"Error al completar compra {compra_id} y actualizar stock: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Ocurrió un error al completar la compra y actualizar el stock.")