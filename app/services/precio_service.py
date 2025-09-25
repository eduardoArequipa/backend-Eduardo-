from decimal import Decimal
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func
from ..models.producto import Producto as DBProducto
from ..models.detalle_compra import DetalleCompra as DBDetalleCompra
from ..models.compra import Compra as DBCompra
from ..models.conversion import Conversion as DBConversion
from ..models.enums import EstadoCompraEnum, TipoMargenEnum
import logging

logger = logging.getLogger(__name__)

class PrecioService:
    
    @staticmethod
    def calcular_precio_compra_promedio_ponderado(db: Session, producto_id: int) -> Decimal:
        """
        Calcula el precio de compra promedio ponderado basado en las compras completadas.
        CORREGIDO: Considera las conversiones para calcular el precio por unidad base.
        Usa la fórmula: (Σ(precio_presentacion)) / Σ(cantidad_unidades_base)
        """
        try:
            # Obtener todas las compras completadas para este producto con conversiones
            detalles = db.query(DBDetalleCompra).options(
                joinedload(DBDetalleCompra.producto).joinedload(DBProducto.conversiones)
            ).join(DBCompra).filter(
                DBDetalleCompra.producto_id == producto_id,
                DBCompra.estado == EstadoCompraEnum.completada
            ).all()
            
            if not detalles:
                # Si no hay compras, mantener el precio actual
                producto = db.query(DBProducto).filter(DBProducto.producto_id == producto_id).first()
                return producto.precio_compra if producto else Decimal('0.00')
            
            total_costo = Decimal('0.00')
            total_unidades_base = Decimal('0.00')
            
            for detalle in detalles:
                # Precio de la presentación (ej: 1000 Bs por caja)
                precio_presentacion = Decimal(str(detalle.precio_unitario))
                cantidad_presentacion = Decimal(str(detalle.cantidad))
                
                # Factor de conversión (ej: 100 unidades por caja)
                conversion_factor = Decimal('1')  # Por defecto 1 (unidad base)
                
                if detalle.presentacion_compra and detalle.presentacion_compra.strip():
                    presentacion_nombre = detalle.presentacion_compra.strip().lower()
                    
                    # Buscar la conversión correspondiente
                    conversion = next((c for c in detalle.producto.conversiones 
                                     if c.nombre_presentacion.lower() == presentacion_nombre 
                                     and c.es_para_compra), None)
                    
                    if conversion and conversion.unidades_por_presentacion > 0:
                        conversion_factor = Decimal(str(conversion.unidades_por_presentacion))
                
                # Calcular unidades base compradas (ej: 1 caja × 100 = 100 tijeras)
                unidades_base = cantidad_presentacion * conversion_factor
                
                # Acumular totales
                total_costo += precio_presentacion * cantidad_presentacion  # Total gastado
                total_unidades_base += unidades_base  # Total unidades base obtenidas
            
            if total_unidades_base > 0:
                # Precio promedio por unidad base (ej: 1000 Bs ÷ 100 tijeras = 10 Bs/tijera)
                precio_promedio = total_costo / total_unidades_base
                return precio_promedio.quantize(Decimal('0.01'))  # Redondear a 2 decimales
            else:
                # Si no hay unidades, mantener el precio actual
                producto = db.query(DBProducto).filter(DBProducto.producto_id == producto_id).first()
                return producto.precio_compra if producto else Decimal('0.00')
                
        except Exception as e:
            logger.error(f"Error calculando precio promedio ponderado para producto {producto_id}: {e}")
            # En caso de error, mantener el precio actual
            producto = db.query(DBProducto).filter(DBProducto.producto_id == producto_id).first()
            return producto.precio_compra if producto else Decimal('0.00')
    
    @staticmethod
    def actualizar_precio_compra_y_venta(db: Session, producto_id: int):
        """
        Actualiza el precio de compra (promedio ponderado) y recalcula el precio de venta automáticamente.
        """
        try:
            producto = db.query(DBProducto).filter(DBProducto.producto_id == producto_id).first()
            if not producto:
                logger.warning(f"Producto {producto_id} no encontrado para actualizar precios")
                return
            
            # Calcular nuevo precio de compra promedio
            nuevo_precio_compra = PrecioService.calcular_precio_compra_promedio_ponderado(db, producto_id)
            
            # Actualizar precio de compra
            producto.precio_compra = nuevo_precio_compra
            
            # Actualizar precio de venta automáticamente si no está en modo manual
            producto.actualizar_precio_venta_automatico()
            
            db.commit()
            
            logger.info(f"Precios actualizados para producto {producto_id}: "
                       f"Compra={nuevo_precio_compra}, Venta={producto.precio_venta}")
            
        except Exception as e:
            logger.error(f"Error actualizando precios para producto {producto_id}: {e}")
            db.rollback()
            raise
    
    @staticmethod
    def actualizar_precios_por_compra(db: Session, compra_id: int):
        """
        Actualiza los precios de todos los productos afectados por una compra completada.
        """
        try:
            # Obtener todos los productos de esta compra
            productos_afectados = db.query(DBDetalleCompra.producto_id).filter(
                DBDetalleCompra.compra_id == compra_id
            ).distinct().all()
            
            for (producto_id,) in productos_afectados:
                PrecioService.actualizar_precio_compra_y_venta(db, producto_id)
            
            logger.info(f"Precios actualizados para {len(productos_afectados)} productos de la compra {compra_id}")
            
        except Exception as e:
            logger.error(f"Error actualizando precios por compra {compra_id}: {e}")
            raise
    
    @staticmethod
    def calcular_precio_venta_sugerido(precio_compra: Decimal, tipo_margen: str, margen_valor: Decimal) -> Decimal:
        """
        Calcula el precio de venta sugerido basado en un precio de compra y margen dados.
        Útil para previsualizaciones en el frontend.
        """
        try:
            if tipo_margen == TipoMargenEnum.porcentaje:
                precio_calculado = precio_compra * (1 + margen_valor / 100)
            else:  # fijo
                precio_calculado = precio_compra + margen_valor
            
            # Nunca permitir precio menor al de compra
            return max(precio_calculado, precio_compra).quantize(Decimal('0.01'))
            
        except Exception as e:
            logger.error(f"Error calculando precio de venta sugerido: {e}")
            return precio_compra
    
    @staticmethod
    def validar_precio_venta_minimo(precio_compra: Decimal, precio_venta: Decimal) -> bool:
        """
        Valida que el precio de venta no sea menor al precio de compra.
        """
        return precio_venta >= precio_compra
    
    @staticmethod
    def convertir_precio_por_presentacion(db: Session, producto_id: int, precio_presentacion: Decimal, unidades_por_presentacion: Decimal) -> Decimal:
        """
        Convierte el precio de una presentación al precio por unidad individual.
        Ejemplo: Si compras 1 caja (100 tijeras) a 1000bs, cada tijera cuesta 10bs.
        """
        try:
            if unidades_por_presentacion <= 0:
                raise ValueError("Las unidades por presentación deben ser mayor a 0")
            
            precio_por_unidad = precio_presentacion / unidades_por_presentacion
            return precio_por_unidad.quantize(Decimal('0.01'))
            
        except Exception as e:
            logger.error(f"Error convirtiendo precio por presentación para producto {producto_id}: {e}")
            raise