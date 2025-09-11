from decimal import Decimal
from typing import Optional, Tuple, List, Dict
from ..models.producto import Producto as DBProducto
from ..schemas.producto import StockConvertido

class DesglosePresentacion:
    """Clase para representar el desglose detallado del stock"""
    def __init__(self, nombre: str, cantidad: int, abreviatura: str = ""):
        self.nombre = nombre
        self.cantidad = cantidad
        self.abreviatura = abreviatura or nombre[:3].upper()

def calcular_stock_desglosado(producto: DBProducto) -> Optional[List[DesglosePresentacion]]:
    """
    Calcula el stock desglosado en todas las presentaciones de venta.
    
    Ejemplo: 515 metros -> [1 caja, 1 rollo, 5 metros]
    
    Lógica:
    1. Ordena conversiones de mayor a menor unidades_por_presentacion
    2. Calcula cuántas unidades completas de cada presentación
    3. Va restando del stock restante
    4. Incluye la unidad base si queda residuo
    """
    if not producto.conversiones or producto.stock <= 0:
        return None
    
    # Filtrar solo conversiones para venta activas
    conversiones_venta = [
        conv for conv in producto.conversiones 
        if conv.es_para_venta and conv.es_activo
    ]
    
    if not conversiones_venta:
        return None
    
    # Ordenar conversiones de mayor a menor unidades_por_presentacion
    conversiones_ordenadas = sorted(
        conversiones_venta, 
        key=lambda x: x.unidades_por_presentacion,
        reverse=True  # De mayor a menor
    )
    
    desglose = []
    stock_restante = float(producto.stock)
    
    # Calcular para cada presentación
    for conversion in conversiones_ordenadas:
        unidades_por_presentacion = float(conversion.unidades_por_presentacion)
        cantidad = int(stock_restante // unidades_por_presentacion)
        
        if cantidad > 0:
            desglose.append(DesglosePresentacion(
                nombre=conversion.nombre_presentacion,
                cantidad=cantidad,
                abreviatura=conversion.nombre_presentacion[:3].upper()
            ))
            stock_restante -= cantidad * unidades_por_presentacion
    
    # Si queda residuo, agregar en unidad base
    if stock_restante > 0:
        desglose.append(DesglosePresentacion(
            nombre=producto.unidad_inventario.nombre_unidad,
            cantidad=int(stock_restante),
            abreviatura=producto.unidad_inventario.abreviatura
        ))
    
    return desglose if desglose else None

def calcular_stock_convertido(producto: DBProducto) -> Optional[StockConvertido]:
    if not producto.conversiones or producto.stock <= 0:
        return None
    
    # Filtrar solo conversiones para venta activas
    conversiones_venta = [
        conv for conv in producto.conversiones 
        if conv.es_para_venta and conv.es_activo
    ]
    
    if not conversiones_venta:
        return None
    
    # Buscar la conversión con mayor unidades_por_presentacion (presentación más grande)
    conversion_preferida = max(
        conversiones_venta, 
        key=lambda x: x.unidades_por_presentacion
    )
    
    # Calcular cuántas unidades completas de esta presentación tenemos
    cantidad_convertida = producto.stock // conversion_preferida.unidades_por_presentacion
    
    # Si no alcanza ni para una unidad de la presentación más grande, 
    # buscar la siguiente presentación más pequeña
    if cantidad_convertida == 0:
        # Ordenar conversiones de menor a mayor unidades_por_presentacion
        conversiones_ordenadas = sorted(
            conversiones_venta, 
            key=lambda x: x.unidades_por_presentacion
        )
        
        for conversion in conversiones_ordenadas:
            cantidad_convertida = producto.stock // conversion.unidades_por_presentacion
            if cantidad_convertida > 0:
                conversion_preferida = conversion
                break
        
        # Si aún no hay cantidad suficiente, mostrar en unidad base
        if cantidad_convertida == 0:
            return StockConvertido(
                cantidad=producto.stock,
                unidad_nombre=producto.unidad_inventario.nombre_unidad,
                unidad_abreviatura=producto.unidad_inventario.abreviatura,
                es_aproximado=False
            )
    
    # Verificar si la conversión es exacta
    resto = producto.stock % conversion_preferida.unidades_por_presentacion
    es_aproximado = resto > 0
    
    return StockConvertido(
        cantidad=cantidad_convertida,
        unidad_nombre=conversion_preferida.nombre_presentacion,
        unidad_abreviatura=conversion_preferida.nombre_presentacion[:3].upper(),  # Abreviatura simple
        es_aproximado=es_aproximado
    )

def obtener_mensaje_stock_detallado(producto: DBProducto) -> str:
    """
    Genera un mensaje detallado del stock para mostrar en tooltips o descripciones.
    
    Ejemplo: "100 metros = 10 rollos (5 cajas no completas)"
    """
    if not producto.conversiones or producto.stock <= 0:
        return f"{producto.stock} {producto.unidad_inventario.abreviatura}"
    
    stock_convertido = calcular_stock_convertido(producto)
    if not stock_convertido:
        return f"{producto.stock} {producto.unidad_inventario.abreviatura}"
    
    # Construir mensaje base
    mensaje = f"{producto.stock} {producto.unidad_inventario.abreviatura}"
    
    if stock_convertido.cantidad > 0:
        mensaje += f" = {stock_convertido.cantidad} {stock_convertido.unidad_nombre}"
        
        if stock_convertido.es_aproximado:
            mensaje += " (aprox.)"
    
    return mensaje