from typing import List, Optional, Union
from datetime import datetime, timezone # Importar timezone
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import or_, and_

# Importa módulos para la notificación (Twilio o simulación)
import os
import logging

# *** Importa la librería de Twilio ***
from twilio.rest import Client
from twilio.base.exceptions import TwilioRestException # Para manejar errores de Twilio


logger = logging.getLogger(__name__)


# O usando un archivo .env y python-dotenv (ver documentación)
account_sid = os.environ.get('TWILIO_ACCOUNT_SID')
auth_token = os.environ.get('TWILIO_AUTH_TOKEN')
twilio_phone_number_sms = os.environ.get('TWILIO_PHONE_NUMBER') # Número para SMS/llamadas si aplica
twilio_whatsapp_from = os.environ.get('TWILIO_WHATSAPP_FROM') # Número de Twilio/Sandbox para WhatsApp (ej. "whatsapp:+1415238886")


# Inicializa el cliente de Twilio (solo si las credenciales están disponibles)
twilio_client = None
if account_sid and auth_token:
    try:
        twilio_client = Client(account_sid, auth_token)
        logger.info("Cliente de Twilio inicializado correctamente.")
    except Exception as e:
        logger.error(f"Error al inicializar cliente de Twilio: {e}")
        twilio_client = None # Asegura que el cliente es None si falla la inicialización
else:
    logger.warning("Variables de entorno TWILIO_ACCOUNT_SID o TWILIO_AUTH_TOKEN no configuradas. El envío de mensajes estará deshabilitado.")


# Importa tus utilidades de auth y la dependencia get_db
from .. import auth as auth_utils

from ..database import get_db

# Importa los modelos SQLAlchemy
from ..models.compra import Compra as DBCompra
from ..models.detalle_compra import DetalleCompra as DBDetalleCompra
from ..models.producto import Producto as DBProducto # Necesario para actualizar stock
from ..models.proveedor import Proveedor as DBProveedor # Necesario para obtener info del proveedor
from ..models.usuario import Usuario as DBUsuario # Necesario para relaciones de usuario y auditoría
from ..models.persona import Persona as DBPersona
from ..models.empresa import Empresa as DBEmpresa


# Importa el Enum para el estado de compra
from ..models.enums import EstadoCompraEnum , EstadoEnum# Asegúrate de que EstadoCompraEnum existe aquí

# Importar tus esquemas Pydantic
from ..schemas.compra import (
    Compra, # Esquema de lectura completa
    CompraCreate, # Esquema para creación (con detalles anidados)
    CompraUpdate, # Esquema para actualización (solo estado por ahora)
    DetalleCompraCreate, # Esquema para crear detalles (usado en CompraCreate)
    DetalleCompra # Esquema de lectura de detalle (usado en Compra)
)

# Importa esquemas anidados si son necesarios para la respuesta (ej. ProveedorNested, UsuarioAudit, ProductoNested)
from ..schemas.proveedor import ProveedorNested
from ..schemas.usuario import UsuarioAudit
from ..schemas.producto import ProductoCompra # Asegúrate que este esquema incluye precio_compra si lo necesitas en la respuesta


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


    # *** Lógica de Envío (Twilio WhatsApp o Simulación) ***
    # Verificar si tenemos un número de teléfono, un cliente de Twilio inicializado Y el número de origen de WhatsApp configurado
    if telefono_proveedor and twilio_client and twilio_whatsapp_from:
        # Asegúrate de que el número de destino está en formato E.164 (+<codigo_pais><numero>)
        # Si no estás seguro del formato, podrías necesitar validar/formatear aquí
        # Para Twilio WhatsApp, el número de destino también debe tener el prefijo "whatsapp:"
        telefono_destino_whatsapp = f"whatsapp:{telefono_proveedor}"

        try:
            # *** Llamada REAL a la API de Twilio para WhatsApp ***
            message = twilio_client.messages.create(
                body=mensaje,
                # *** VERIFICA QUE ESTA LÍNEA USA twilio_whatsapp_from ***
                from_=twilio_whatsapp_from, # <-- DEBE SER EL NÚMERO DEL SANDBOX CON PREFIJO
                to=telefono_destino_whatsapp # El número del proveedor en formato WhatsApp
            )
            logger.info(f"Mensaje de Twilio WhatsApp enviado a {telefono_destino_whatsapp} (Proveedor: {nombre_proveedor}). SID: {message.sid}")
        except TwilioRestException as e:
            logger.error(f"Error al enviar mensaje de Twilio WhatsApp a {telefono_destino_whatsapp} (Proveedor: {nombre_proveedor}): {e}")
            # TwilioRestException puede tener códigos de error específicos, puedes manejarlos si es necesario
            # if e.code == 21610: # Error: The 'To' number is not currently reachable via WhatsApp.
            #     logger.warning(f"Número de proveedor {telefono_proveedor} no válido para WhatsApp.")
        except Exception as e:
            logger.error(f"Error inesperado al intentar enviar mensaje de Twilio WhatsApp a {telefono_destino_whatsapp} (Proveedor: {nombre_proveedor}): {e}")
    elif telefono_proveedor: # Si hay número pero Twilio WhatsApp no está configurado
        # --- SIMULACIÓN DE ENVÍO EN DESARROLLO ---
        logger.info(f"SIMULACIÓN ENVÍO MENSAJE: A={telefono_proveedor} (Proveedor: {nombre_proveedor}), Mensaje:\n{mensaje}") # Imprime el mensaje completo en la simulación
    # --- FIN SIMULACIÓN ---
    else:
        logger.warning(f"No se pudo enviar mensaje al proveedor {nombre_proveedor} (ID: {proveedor_id}): Teléfono no disponible.")



# --- Endpoint para Crear una Nueva Compra ---
@router.post("/", response_model=Compra, status_code=status.HTTP_201_CREATED)
def create_compra(
    compra_data: CompraCreate,
    db: Session = Depends(get_db),
    current_user: auth_utils.Usuario = Depends(auth_utils.get_current_active_user_with_role(ROLES_CAN_MANAGE_COMPRAS))
):
    """
    Crea una nueva Compra con sus detalles, actualiza el stock de productos
    y opcionalmente notifica al proveedor por WhatsApp (si Twilio está configurado).
    Solo accesible por usuarios con permisos de gestión de compras.
    """
    db.begin_nested() # Inicia una transacción anidada para asegurar la atomicitad

    try:
        # 1. Verificar que el Proveedor existe y está activo
        db_proveedor = db.query(DBProveedor).filter(
            DBProveedor.proveedor_id == compra_data.proveedor_id,
            DBProveedor.estado == EstadoEnum.activo # Asume EstadoEnum.activo si usas el mismo Enum
        ).first()
        if db_proveedor is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Proveedor con ID {compra_data.proveedor_id} no encontrado o inactivo.")

        # 2. Eliminado: La verificación del usuario que registra la compra es manejada por current_user

        # 3. Validar y procesar los detalles de la compra
        if not compra_data.detalles:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="La compra debe tener al menos un detalle.")

        total_compra = Decimal(0)
        db_detalles = []
        productos_a_actualizar_stock = {}

        for detalle_data in compra_data.detalles:
            db_producto = db.query(DBProducto).filter(
                DBProducto.producto_id == detalle_data.producto_id,
                DBProducto.estado == EstadoEnum.activo # Asume EstadoEnum.activo
            ).first()
            if db_producto is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Producto con ID {detalle_data.producto_id} en el detalle no encontrado o inactivo.")

            if detalle_data.cantidad <= 0:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"La cantidad para el producto ID {detalle_data.producto_id} debe ser positiva.")

            # Lógica para jalar precio_compra y permitir modificación
            # Si precio_unitario NO fue proporcionado o es 0, usa el precio_compra del producto
            # De lo contrario, usa el precio_unitario proporcionado (permitiendo modificarlo)
            precio_unitario_final = detalle_data.precio_unitario
            if precio_unitario_final is None or precio_unitario_final == Decimal(0):
                if db_producto.precio_compra is not None:
                    precio_unitario_final = db_producto.precio_compra
                else:
                    # Si el precio de compra del producto no está definido, y no se proporcionó uno
                    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"El producto '{db_producto.nombre}' (ID: {db_producto.producto_id}) no tiene un precio de compra definido y no se proporcionó un precio unitario para el detalle.")
            
            # Asegurar que el precio unitario final no sea negativo
            if precio_unitario_final < 0:
                 raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"El precio unitario final para el producto ID {detalle_data.producto_id} no puede ser negativo.")

            subtotal_detalle = detalle_data.cantidad * precio_unitario_final
            total_compra += subtotal_detalle

            db_detalle = DBDetalleCompra(
                producto_id=detalle_data.producto_id,
                cantidad=detalle_data.cantidad,
                precio_unitario=precio_unitario_final # Usar el precio_unitario_final
            )

            db_detalles.append(db_detalle)

            productos_a_actualizar_stock[detalle_data.producto_id] = productos_a_actualizar_stock.get(detalle_data.producto_id, 0) + detalle_data.cantidad


        # 4. Crear el objeto Compra SQLAlchemy
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
        db.flush() # Aplica los cambios a la base de datos de manera provisional para obtener el ID de la compra

        # 5. Actualizar el stock de los productos
        for producto_id, cantidad_comprada in productos_a_actualizar_stock.items():
             db_producto = db.query(DBProducto).filter(DBProducto.producto_id == producto_id).first()
             if db_producto:
                  db_producto.stock = (db_producto.stock or 0) + cantidad_comprada
                  db.add(db_producto)

        # 6. Confirmar la transacción
        db.commit() # Guarda todos los cambios permanentemente en la base de datos

        # 7. Notificar al proveedor (opcional y fuera de la transacción principal)
        try:
            # db.refresh(nueva_compra) no es estrictamente necesario aquí si ya se hizo flush y commit.
            # Los joinedloads en la consulta final son más importantes.
            # Asegurarse de que el objeto `nueva_compra` tiene el ID asignado por la DB después del commit.
            notify_proveedor(db, nueva_compra.compra_id, nueva_compra.proveedor_id, nueva_compra.total)
        except Exception as e:
            logger.error(f"Error al intentar notificar al proveedor para compra {nueva_compra.compra_id}: {e}")


        # 8. Refrescar la compra para obtener los datos completos para la respuesta
        # Asegurarse de cargar todas las relaciones para el response_model de FastAPI
        db_compra_for_response = db.query(DBCompra).options(
            joinedload(DBCompra.proveedor).joinedload(DBProveedor.persona),
            joinedload(DBCompra.proveedor).joinedload(DBProveedor.empresa),
            joinedload(DBCompra.creador),
            joinedload(DBCompra.modificador),
            joinedload(DBCompra.detalles).joinedload(DBDetalleCompra.producto)
        ).filter(DBCompra.compra_id == nueva_compra.compra_id).first()


        return db_compra_for_response

    except HTTPException as e:
        db.rollback() # Revertir todos los cambios en caso de HTTPException
        raise e
    except Exception as e:
        db.rollback() # Revertir todos los cambios en caso de cualquier otro error
        print(f"Error durante la creación de Compra: {e}") # Mantener para depuración rápida en consola
        logger.error(f"Error inesperado durante la creación de Compra: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Ocurrió un error al crear la Compra.")


# --- Endpoint para Listar Compras ---
@router.get("/", response_model=List[Compra])
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
    current_user: auth_utils.Usuario = Depends(auth_utils.get_current_active_user_with_role(ROLES_CAN_MANAGE_COMPRAS))
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

    # Aplicar paginación
    compras = query.offset(skip).limit(limit).all()

    return compras
# --- Endpoint para Obtener una Compra por ID ---
@router.get("/{compra_id}", response_model=Compra) # Retorna el esquema Compra
def read_compra(
    compra_id: int,
    db: Session = Depends(get_db),
    current_user: auth_utils.Usuario = Depends(auth_utils.get_current_active_user_with_role(ROLES_CAN_MANAGE_COMPRAS))
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
    compra_update: CompraUpdate, # Espera el esquema CompraUpdate (ahora con detalles opcionales)
    db: Session = Depends(get_db),
    current_user: auth_utils.Usuario = Depends(auth_utils.get_current_active_user_with_role(ROLES_CAN_MANAGE_COMPRAS))
):
    """
    Actualiza la información de una Compra existente por su ID, incluyendo sus detalles y ajustando el stock.
    Solo accesible por usuarios con permisos de gestión de compras.
    """
    db.begin_nested() # Iniciar una transacción anidada para manejar los cambios de stock y detalles

    try:
        # 1. Obtener la compra por ID con todas sus relaciones necesarias
        db_compra = db.query(DBCompra).options(
            joinedload(DBCompra.proveedor).joinedload(DBProveedor.persona),
            joinedload(DBCompra.proveedor).joinedload(DBProveedor.empresa),
            joinedload(DBCompra.creador),
            joinedload(DBCompra.modificador),
            joinedload(DBCompra.detalles).joinedload(DBDetalleCompra.producto) # Cargar los detalles y sus productos
        ).filter(DBCompra.compra_id == compra_id).first()

        if db_compra is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Compra no encontrada.")

        # No permitir modificación si la compra ya está completada o anulada
        if db_compra.estado in [EstadoCompraEnum.completada, EstadoCompraEnum.anulada]:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"No se puede modificar una compra en estado '{db_compra.estado.value}'.")

        # 2. Actualizar campos principales de la Compra (proveedor_id, fecha_compra, estado)
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


        # 3. Manejar la actualización de los detalles de la compra y el stock
        if compra_update.detalles is not None: # Solo si se enviaron detalles en el payload
            
            # Para consolidar cambios de stock
            productos_stock_change = {} # {producto_id: cambio_neto_stock}

            # Paso 1: Revertir el stock de todos los detalles existentes
            for db_detalle in db_compra.detalles:
                productos_stock_change[db_detalle.producto_id] = productos_stock_change.get(db_detalle.producto_id, 0) - db_detalle.cantidad

            # Paso 2: Eliminar todos los detalles existentes de la compra
            # Iterar sobre una copia para evitar problemas de concurrencia al modificar la colección
            for db_detalle in list(db_compra.detalles):
                db.delete(db_detalle)

            db.flush() # Asegura que las eliminaciones se registren antes de añadir nuevos detalles

            # Paso 3: Añadir los nuevos detalles y registrar sus cambios de stock
            new_db_detalles = []
            for incoming_detalle_data in compra_update.detalles:
                # Validar que el producto existe y está activo
                db_producto = db.query(DBProducto).filter(
                    DBProducto.producto_id == incoming_detalle_data.producto_id,
                    DBProducto.estado == EstadoEnum.activo
                ).first()
                if db_producto is None:
                    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Producto con ID {incoming_detalle_data.producto_id} en el detalle no encontrado o inactivo.")

                if incoming_detalle_data.cantidad <= 0:
                    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"La cantidad para el producto ID {incoming_detalle_data.producto_id} debe ser positiva.")

                # Lógica para jalar precio_compra y permitir modificación
                precio_unitario_final = incoming_detalle_data.precio_unitario
                if precio_unitario_final is None or precio_unitario_final == Decimal(0):
                    if db_producto.precio_compra is not None:
                        precio_unitario_final = db_producto.precio_compra
                    else:
                        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"El producto '{db_producto.nombre}' (ID: {db_producto.producto_id}) no tiene un precio de compra definido y no se proporcionó un precio unitario para el detalle.")
                
                # Asegurar que el precio unitario final no sea negativo
                if precio_unitario_final < 0:
                    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"El precio unitario final para el producto ID {incoming_detalle_data.producto_id} no puede ser negativo.")

                new_db_detalle = DBDetalleCompra(
                    producto_id=incoming_detalle_data.producto_id,
                    cantidad=incoming_detalle_data.cantidad,
                    precio_unitario=precio_unitario_final # Usar el precio_unitario_final
                )
                new_db_detalles.append(new_db_detalle)
                
                # Sumar al stock el nuevo producto
                productos_stock_change[incoming_detalle_data.producto_id] = productos_stock_change.get(incoming_detalle_data.producto_id, 0) + incoming_detalle_data.cantidad

            # Añadir todos los nuevos detalles a la compra
            db_compra.detalles.extend(new_db_detalles)
            db.flush() # Asegurar que los nuevos detalles estén asociados y tengan IDs si son necesarios para el cálculo total

            # Aplicar los cambios de stock consolidados
            for producto_id, change in productos_stock_change.items():
                db_producto = db.query(DBProducto).filter(DBProducto.producto_id == producto_id).first()
                if db_producto:
                    db_producto.stock = (db_producto.stock or 0) + change
                    db.add(db_producto) # Marcar para guardar cambios en el producto
                else:
                    logger.warning(f"Producto con ID {producto_id} no encontrado al intentar ajustar stock para la compra {compra_id}.")


            # Recalcular el total de la compra basado en los nuevos/actualizados detalles
            db.flush() # Asegurar que los detalles se han actualizado en la sesión para recalcular
            new_total = Decimal(0)
            # Cargar los detalles de la compra de nuevo para asegurar que están actualizados en la sesión
            db.refresh(db_compra, attribute_names=['detalles'])
            for detalle in db_compra.detalles:
                new_total += Decimal(str(detalle.cantidad)) * Decimal(str(detalle.precio_unitario))
            db_compra.total = new_total

        # 4. Asignar el usuario modificador
        db_compra.modificado_por = current_user.usuario_id

        db.commit() # Confirmar todos los cambios (compra principal, detalles, stock)
        db.refresh(db_compra) # Refrescar para obtener los cambios confirmados

        # 5. Cargar las relaciones necesarias para el response_model
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
        print(f"Error durante la actualización de Compra {compra_id}: {e}") # Mantener para depuración rápida en consola
        logger.error(f"Error inesperado durante la actualización de Compra {compra_id}: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Ocurrió un error al actualizar la Compra.")

@router.patch("/{compra_id}/anular", response_model=Compra)
def anular_compra(
    compra_id: int,
    db: Session = Depends(get_db),
    current_user: auth_utils.Usuario = Depends(auth_utils.get_current_active_user_with_role(ROLES_CAN_MANAGE_COMPRAS))
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
        db.begin_nested() # Iniciar transacción anidada para la reversión de stock

        for detalle in db_compra.detalles:
            db_producto = db.query(DBProducto).filter(DBProducto.producto_id == detalle.producto_id).first()
            if db_producto:
                # Restar stock, asegurando no bajar de 0 si tu negocio lo requiere
                if (db_producto.stock or 0) < detalle.cantidad:
                     logger.warning(f"Intentando revertir stock para Producto ID {detalle.producto_id} (Compra {compra_id}), pero el stock actual ({db_producto.stock or 0}) es menor que la cantidad a restar ({detalle.cantidad}). Esto podría llevar a stock negativo.")

                db_producto.stock = (db_producto.stock or 0) - detalle.cantidad
                db.add(db_producto) # Marca el producto como modificado

        # Cambiar el estado de la compra a 'anulada'
        db_compra.estado = EstadoCompraEnum.anulada
        db_compra.modificado_por = current_user.usuario_id # Registrar quién modificó

        db.commit() # Confirmar los cambios (estado y stock)
        db.refresh(db_compra) # Refrescar para obtener los cambios confirmados

        return db_compra # Retornar el objeto de compra actualizado

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
    current_user: auth_utils.Usuario = Depends(auth_utils.get_current_active_user_with_role(ROLES_CAN_MANAGE_COMPRAS))
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
    if db_compra.estado == EstadoCompraEnum.anulada: # No permitir completar una compra anulada
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No se puede completar una compra anulada.")

    try:
        db.begin_nested() # Iniciar transacción anidada para la actualización de stock

        for detalle in db_compra.detalles:
            db_producto = db.query(DBProducto).filter(DBProducto.producto_id == detalle.producto_id).first()
            if db_producto:
                db_producto.stock = (db_producto.stock or 0) + detalle.cantidad # Sumar al stock
                db_producto.modificado_por = current_user.usuario_id
                db.add(db_producto) # Marca el producto como modificado

        # Cambiar el estado de la compra a 'completada'
        db_compra.estado = EstadoCompraEnum.completada
        db_compra.modificado_por = current_user.usuario_id # Registrar quién modificó

        db.commit() # Confirmar los cambios (estado y stock)
        db.refresh(db_compra) # Refrescar para obtener los cambios confirmados

        return db_compra # Retornar el objeto de compra actualizado

    except HTTPException as e:
        db.rollback()
        raise e
    except Exception as e:
        db.rollback()
        logger.error(f"Error al completar compra {compra_id} y actualizar stock: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Ocurrió un error al completar la compra y actualizar el stock.")
