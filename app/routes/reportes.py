from fastapi import APIRouter, Depends, Query, HTTPException, Response
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func, and_, text, extract, case, desc
from typing import List, Optional
from datetime import datetime, timedelta
from decimal import Decimal
import io

# Importaciones de ReportLab
from reportlab.lib.pagesizes import letter, landscape
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib import colors
from reportlab.lib.units import inch

# Importaciones de la aplicación
from ..database import get_db
from .. import auth
from ..models.venta import Venta
from ..models.detalle_venta import DetalleVenta
from ..models.compra import Compra
from ..models.detalle_compra import DetalleCompra
from ..models.producto import Producto
from ..models.persona import Persona
from ..models.usuario import Usuario
from ..models.categoria import Categoria
from ..models.proveedor import Proveedor
from ..models.marca import Marca
from ..models.metodo_pago import MetodoPago
from ..models.empresa import Empresa
from .. import auth as auth_utils
from ..schemas.reportes import (
    FiltroReporteVentas, FiltroReporteCompras, FiltroReporteProductos,
    ReporteVentasResponse, ReporteComprasResponse, ReporteProductosResponse,
    ReporteVentaItem, ReporteCompraItem, ReporteProductoItem,
    ResumenVentas, ResumenCompras, ResumenProductos
) 


router = APIRouter(
    prefix="/reportes",
    tags=["reportes"]
)

# Roles que pueden acceder a este endpoint
ROLES_CAN_ACCESS_REPORTS = ["Administrador", "Empleado"]

def get_empresa_info(db: Session) -> dict:
    """
    Obtiene la información de la empresa principal (no proveedores) para incluir en los reportes.
    """
    try:
        # Buscar "COMERCIAL DON EDUARDO" que NO sea un proveedor
        empresa_principal = db.query(Empresa).outerjoin(
            Proveedor, Empresa.empresa_id == Proveedor.empresa_id
        ).filter(
            Empresa.razon_social.ilike("%COMERCIAL DON EDUARDO%"),
            Empresa.estado == "activo",
            Proveedor.empresa_id.is_(None)  # No es un proveedor
        ).first()
        
        if empresa_principal:
            return {
                "razon_social": empresa_principal.razon_social,
                "identificacion": empresa_principal.identificacion,
                "direccion": empresa_principal.direccion,
                "telefono": empresa_principal.telefono,
                "email": empresa_principal.email
            }
        
        # Si no encuentra "COMERCIAL DON EDUARDO" que no sea proveedor,
        # buscar el que tiene la dirección correcta (sin importar si es proveedor)
        empresa_con_direccion = db.query(Empresa).filter(
            Empresa.razon_social.ilike("%COMERCIAL DON EDUARDO%"),
            Empresa.direccion.ilike("%Circunvalación%"),
            Empresa.estado == "activo"
        ).first()
        
        if empresa_con_direccion:
            return {
                "razon_social": empresa_con_direccion.razon_social,
                "identificacion": empresa_con_direccion.identificacion,
                "direccion": empresa_con_direccion.direccion,
                "telefono": empresa_con_direccion.telefono,
                "email": empresa_con_direccion.email
            }
            
    except Exception as e:
        print(f"Error al obtener información de la empresa: {e}")
    
    # Retornar None si no se encuentra empresa principal
    return None

def get_usuario_info(user: Usuario) -> dict:
    """
    Obtiene la información del usuario para incluir en los reportes.
    """
    return {
        "nombre_usuario": user.nombre_usuario,
        "email": user.email if hasattr(user, 'email') else None,
        "usuario_id": user.usuario_id
    }

def get_periodo_fechas(periodo_tipo: str, fecha_desde: Optional[datetime], fecha_hasta: Optional[datetime]) -> tuple:
    """Calcula las fechas según el tipo de periodo"""
    if fecha_desde and fecha_hasta:
        return fecha_desde, fecha_hasta
    
    ahora = datetime.now()
    if periodo_tipo == "dia":
        inicio = ahora.replace(hour=0, minute=0, second=0, microsecond=0)
        fin = inicio + timedelta(days=1) - timedelta(microseconds=1)
    elif periodo_tipo == "mes":
        inicio = ahora.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        if ahora.month == 12:
            fin = ahora.replace(year=ahora.year+1, month=1, day=1) - timedelta(microseconds=1)
        else:
            fin = ahora.replace(month=ahora.month+1, day=1) - timedelta(microseconds=1)
    elif periodo_tipo == "año":
        inicio = ahora.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
        fin = ahora.replace(year=ahora.year+1, month=1, day=1) - timedelta(microseconds=1)
    else:
        # Por defecto, último mes
        inicio = (ahora.replace(day=1) - timedelta(days=1)).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        fin = ahora.replace(day=1) - timedelta(microseconds=1)
    
    return inicio, fin

def format_periodo_string(fecha_desde: datetime, fecha_hasta: datetime, periodo_tipo: Optional[str] = None) -> str:
    """Formatea el string del periodo para mostrar en reportes"""
    if periodo_tipo == "dia":
        return f"Día: {fecha_desde.strftime('%d/%m/%Y')}"
    elif periodo_tipo == "mes":
        return f"Mes: {fecha_desde.strftime('%B %Y')}"
    elif periodo_tipo == "año":
        return f"Año: {fecha_desde.strftime('%Y')}"
    elif fecha_desde and fecha_hasta:
        return f"Periodo: {fecha_desde.strftime('%d/%m/%Y')} al {fecha_hasta.strftime('%d/%m/%Y')}"
    else:
        return "Todos los registros"

def create_report_pdf(data: list, resumen: dict, titulo: str, periodo: str, tipo_reporte: str, 
                      usuario_generador: dict = None, info_empresa: dict = None):
    """
    Genera un reporte profesional en formato PDF usando ReportLab.
    """
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=landscape(letter), leftMargin=0.5*inch, rightMargin=0.5*inch,
                           topMargin=0.75*inch, bottomMargin=0.75*inch)
    
    styles = getSampleStyleSheet()
    elements = []

    # Encabezado de la empresa (solo si está disponible y tiene información)
    if info_empresa and info_empresa.get('razon_social'):
        empresa_title = Paragraph(f"<b>{info_empresa.get('razon_social')}</b>", styles['h1'])
        elements.append(empresa_title)
        
        if info_empresa.get('identificacion'):
            ruc_paragraph = Paragraph(f"RUC: {info_empresa.get('identificacion')}", styles['Normal'])
            elements.append(ruc_paragraph)
        
        if info_empresa.get('direccion'):
            direccion_paragraph = Paragraph(f"Dirección: {info_empresa.get('direccion')}", styles['Normal'])
            elements.append(direccion_paragraph)
        
        if info_empresa.get('telefono'):
            telefono_paragraph = Paragraph(f"Teléfono: {info_empresa.get('telefono')}", styles['Normal'])
            elements.append(telefono_paragraph)
        
        elements.append(Spacer(1, 20))

    # Título principal del reporte
    title = Paragraph(f"<b>{titulo}</b>", styles['h1'])
    elements.append(title)
    
    # Información del reporte
    info_reporte = [
        ["Período:", periodo],
        ["Fecha de Generación:", datetime.now().strftime('%d/%m/%Y %H:%M:%S')],
        ["Generado por:", usuario_generador.get('nombre_usuario', 'Sistema') if usuario_generador else 'Sistema'],
    ]
    
    if usuario_generador and usuario_generador.get('email'):
        info_reporte.append(["Email:", usuario_generador.get('email')])
    
    info_table = Table(info_reporte, colWidths=[2*inch, 4*inch])
    info_table.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
    ]))
    elements.append(info_table)
    elements.append(Spacer(1, 20))
    
    # Resumen ejecutivo
    resumen_title = Paragraph("<b>RESUMEN EJECUTIVO</b>", styles['h2'])
    elements.append(resumen_title)
    elements.append(Spacer(1, 10))
    
    # Crear tabla de resumen según el tipo de reporte
    if tipo_reporte == "ventas":
        resumen_data = [
            ["Total de Ventas:", f" {resumen.get('total_ventas', 0):.2f}"],
            ["Cantidad de Ventas:", str(resumen.get('cantidad_ventas', 0))],
            ["Promedio por Venta:", f" {resumen.get('promedio_venta', 0):.2f}"],
            ["Producto más vendido:", resumen.get('producto_mas_vendido', 'N/A')],
            ["Categoría más vendida:", resumen.get('categoria_mas_vendida', 'N/A')]
        ]
    elif tipo_reporte == "compras":
        resumen_data = [
            ["Total de Compras:", f" {resumen.get('total_compras', 0):.2f}"],
            ["Cantidad de Compras:", str(resumen.get('cantidad_compras', 0))],
            ["Promedio por Compra:", f" {resumen.get('promedio_compra', 0):.2f}"],
            ["Proveedor más frecuente:", resumen.get('proveedor_mas_frecuente', 'N/A')],
            ["Categoría más comprada:", resumen.get('categoria_mas_comprada', 'N/A')]
        ]
    else:  # productos
        resumen_data = [
            ["Total de Productos:", str(resumen.get('total_productos', 0))],
            ["Productos con Stock:", str(resumen.get('productos_con_stock', 0))],
            ["Productos sin Stock:", str(resumen.get('productos_sin_stock', 0))],
            ["Productos Stock Bajo:", str(resumen.get('productos_stock_bajo', 0))],
            ["Valor del Inventario:", f" {resumen.get('valor_inventario', 0):.2f}"]
        ]
    
    resumen_table = Table(resumen_data, colWidths=[3*inch, 2*inch])
    resumen_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (0, -1), colors.lightgrey),
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('GRID', (0, 0), (-1, -1), 1, colors.black),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ]))
    elements.append(resumen_table)
    elements.append(Spacer(1, 20))

    # Detalle del reporte
    detail_title = Paragraph("<b>DETALLE</b>", styles['h2'])
    elements.append(detail_title)
    elements.append(Spacer(1, 10))

    # Definir encabezados según el tipo de reporte
    if tipo_reporte == "ventas":
        headers = ["ID", "Fecha", "Cliente", "Vendedor", "Producto", "Categoría", "Cant.", "P.Unit.", "Subtotal"]
        table_data = [headers]
        
        for row in data:
            cliente_nombre = f"{row.get('cliente_nombre', '')} {row.get('cliente_apellido', '') or ''}".strip() or "N/A"
            table_data.append([
                str(row['venta_id']),
                row['fecha_venta'][:10] if isinstance(row['fecha_venta'], str) else row['fecha_venta'].strftime('%d/%m/%Y'),
                cliente_nombre,
                row.get('vendedor_nombre', 'N/A'),
                row['producto_nombre'],
                row['categoria_nombre'],
                f"{row['cantidad']:.2f}",
                f" {row['precio_unitario']:.2f}",
                f" {float(row['cantidad']) * float(row['precio_unitario']):.2f}"
            ])
    elif tipo_reporte == "compras":
        headers = ["ID", "Fecha", "Proveedor", "Empleado", "Producto", "Categoría", "Cant.", "P.Compra", "Subtotal"]
        table_data = [headers]
        
        for row in data:
            table_data.append([
                str(row['compra_id']),
                row['fecha_compra'][:10] if isinstance(row['fecha_compra'], str) else row['fecha_compra'].strftime('%d/%m/%Y'),
                row['proveedor_nombre'],
                row.get('empleado_nombre', 'N/A'),
                row['producto_nombre'],
                row['categoria_nombre'],
                f"{row['cantidad']:.2f}",
                f"{row['precio_compra']:.2f}",
                f"{float(row['cantidad']) * float(row['precio_compra']):.2f}"
            ])
    else:  # productos
        headers = ["Código", "Producto", "Categoría", "Marca", "Stock", "Stock Mín.", "P.Compra", "P.Venta", "Estado"]
        table_data = [headers]
        
        for row in data:
            table_data.append([
                row['codigo'],
                row['nombre'],
                row['categoria_nombre'],
                row['marca_nombre'],
                f"{row['stock_actual']:.2f}",
                str(row['stock_minimo']),
                f" {row['precio_compra']:.2f}",
                f" {row['precio_venta']:.2f}",
                row['estado']
            ])

    # Crear la tabla principal
    table = Table(table_data, repeatRows=1)
    table_style = [
        ('BACKGROUND', (0, 0), (-1, 0), colors.darkblue),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 8),
        ('FONTSIZE', (0, 1), (-1, -1), 7),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.black),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.lightgrey]),
    ]
    table.setStyle(TableStyle(table_style))
    
    elements.append(table)
    
    # Pie de página profesional
    elements.append(Spacer(1, 30))
    
    # Línea separadora
    separator = Table([[""]], colWidths=[10*inch])
    separator.setStyle(TableStyle([
        ('LINEABOVE', (0, 0), (-1, -1), 2, colors.darkblue),
    ]))
    elements.append(separator)
    elements.append(Spacer(1, 10))
    
    # Información adicional del reporte
    footer_info = [
        ["Total de registros procesados:", str(len(data))],
        ["Sistema:", "Sistema de Gestión Comercial - Versión 1.0"],
        ["Fecha de generación:", datetime.now().strftime('%d/%m/%Y %H:%M:%S')],
    ]
    
    if usuario_generador:
        footer_info.append(["Usuario responsable:", usuario_generador.get('nombre_usuario', 'Sistema')])
    
    # Agregar totales generales según el tipo de reporte
    if tipo_reporte == "ventas" and resumen:
        footer_info.append(["TOTAL GENERAL DE VENTAS:", f" {resumen.get('total_ventas', 0):.2f}"])
        footer_info.append(["Número total de transacciones:", str(resumen.get('cantidad_ventas', 0))])
    elif tipo_reporte == "compras" and resumen:
        footer_info.append(["TOTAL GENERAL DE COMPRAS:", f" {resumen.get('total_compras', 0):.2f}"])
        footer_info.append(["Número total de compras:", str(resumen.get('cantidad_compras', 0))])
    elif tipo_reporte == "productos" and resumen:
        footer_info.append(["VALOR TOTAL DEL INVENTARIO:", f" {resumen.get('valor_inventario', 0):.2f}"])
        footer_info.append(["Productos inventariados:", str(resumen.get('total_productos', 0))])
    
    footer_table = Table(footer_info, colWidths=[3*inch, 4*inch])
    footer_table.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('BACKGROUND', (0, -3), (-1, -1), colors.lightgrey) if len(footer_info) >= 3 else None,
        ('FONTNAME', (0, -3), (-1, -1), 'Helvetica-Bold') if len(footer_info) >= 3 else None,
    ]))
    elements.append(footer_table)
    
    # Nota final
    elements.append(Spacer(1, 15))
    nota_final = Paragraph(
        "<i>Este reporte es confidencial y de uso interno de la empresa. "
        "Los datos mostrados corresponden al período especificado y han sido procesados automáticamente.</i>",
        styles['Normal']
    )
    elements.append(nota_final)
    
    doc.build(elements)
    buffer.seek(0)
    return buffer

@router.get("/ventas", summary="Genera un reporte de ventas detallado en JSON o PDF")
def get_sales_report(
    fecha_desde: Optional[datetime] = Query(None, description="Fecha de inicio (YYYY-MM-DD)"),
    fecha_hasta: Optional[datetime] = Query(None, description="Fecha de fin (YYYY-MM-DD)"),
    producto_ids: Optional[List[int]] = Query(None, description="Lista de IDs de productos a filtrar"),
    categoria_ids: Optional[List[int]] = Query(None, description="Lista de IDs de categorías a filtrar"),
    empleado_ids: Optional[List[int]] = Query(None, description="Lista de IDs de empleados (usuarios) que crearon la venta"),
    formato: str = Query("json", description="Formato de salida: 'json' o 'pdf'"),
    db: Session = Depends(get_db),
    current_user: auth_utils.Usuario = Depends(auth_utils.require_menu_access("/reportes")) # Verificar acceso al menú de categorías
):
    """
    Endpoint para obtener un reporte de ventas con múltiples filtros.
    - **fecha_desde, fecha_hasta**: Rango de fechas para el reporte.
    - **producto_ids**: Filtra ventas que contengan productos específicos.
    - **categoria_ids**: Filtra ventas que contengan productos de categorías específicas.
    - **empleado_ids**: Filtra ventas creadas por empleados específicos.
    - **formato**: Devuelve 'json' por defecto o 'pdf' para descargar un archivo.
    """
    base_query = """
        SELECT
            v.venta_id,
            v.fecha_venta,
            p_cliente.nombre AS cliente_nombre,
            p_cliente.apellido_paterno AS cliente_apellido,
            u_creador.nombre_usuario AS vendedor_nombre,
            dv.cantidad,
            dv.precio_unitario,
            prod.nombre AS producto_nombre,
            cat.nombre_categoria AS categoria_nombre
        FROM
            ventas v
        JOIN
            detalle_ventas dv ON v.venta_id = dv.venta_id
        JOIN
            productos prod ON dv.producto_id = prod.producto_id
        JOIN
            categorias cat ON prod.categoria_id = cat.categoria_id
        LEFT JOIN
            personas p_cliente ON v.persona_id = p_cliente.persona_id
        LEFT JOIN
            usuarios u_creador ON v.creado_por = u_creador.usuario_id
        WHERE
            v.estado = 'activa'
    """
    
    conditions = []
    params = {}

    if fecha_desde:
        conditions.append("v.fecha_venta >= :fecha_desde")
        params["fecha_desde"] = fecha_desde
    if fecha_hasta:
        conditions.append("v.fecha_venta <= :fecha_hasta")
        params["fecha_hasta"] = fecha_hasta
    
    if empleado_ids:
        conditions.append("v.creado_por IN :empleado_ids")
        params["empleado_ids"] = tuple(empleado_ids) # Usar tupla para IN clause
    
    if producto_ids:
        conditions.append("prod.producto_id IN :producto_ids")
        params["producto_ids"] = tuple(producto_ids)
    
    if categoria_ids:
        conditions.append("cat.categoria_id IN :categoria_ids")
        params["categoria_ids"] = tuple(categoria_ids)

    if conditions:
        base_query += " AND " + " AND ".join(conditions)
    
    base_query += " ORDER BY v.fecha_venta DESC"

    result = db.execute(text(base_query), params)
    
    # Mapear los resultados a una lista de diccionarios
    sales_data = []
    for row in result:
        sales_data.append({
            "venta_id": row.venta_id,
            "fecha_venta": row.fecha_venta.strftime('%Y-%m-%d %H:%M'),
            "cliente_nombre": row.cliente_nombre,
            "cliente_apellido": row.cliente_apellido,
            "vendedor_nombre": row.vendedor_nombre,
            "cantidad": row.cantidad,
            "precio_unitario": row.precio_unitario,
            "producto_nombre": row.producto_nombre,
            "categoria_nombre": row.categoria_nombre,
        })

    print(f"DEBUG: Número de ventas encontradas: {len(sales_data)}")
    if sales_data:
        print(f"DEBUG: Primera venta (ID): {sales_data[0]['venta_id'] if sales_data[0] else 'N/A'}")

    if not sales_data:
        raise HTTPException(status_code=404, detail="No se encontraron ventas con los filtros aplicados.")

    # Devolver en el formato solicitado
    if formato.lower() == "pdf":
        start_date_str = fecha_desde.strftime('%Y-%m-%d') if fecha_desde else "Inicio"
        end_date_str = fecha_hasta.strftime('%Y-%m-%d') if fecha_hasta else "Fin"
        
        # Calcular resumen para PDF
        total_ventas = sum(float(row['cantidad']) * float(row['precio_unitario']) for row in sales_data)
        cantidad_ventas = len(set(row['venta_id'] for row in sales_data))
        promedio_venta = total_ventas / cantidad_ventas if cantidad_ventas > 0 else 0
        
        productos_vendidos = {}
        categorias_vendidas = {}
        for row in sales_data:
            productos_vendidos[row['producto_nombre']] = productos_vendidos.get(row['producto_nombre'], 0) + float(row['cantidad'])
            categorias_vendidas[row['categoria_nombre']] = categorias_vendidas.get(row['categoria_nombre'], 0) + float(row['cantidad'])
        
        resumen_dict = {
            'total_ventas': total_ventas,
            'cantidad_ventas': cantidad_ventas,
            'promedio_venta': promedio_venta,
            'producto_mas_vendido': max(productos_vendidos, key=productos_vendidos.get) if productos_vendidos else 'N/A',
            'categoria_mas_vendida': max(categorias_vendidas, key=categorias_vendidas.get) if categorias_vendidas else 'N/A'
        }
        
        periodo_pdf = format_periodo_string(fecha_desde, fecha_hasta, None)
        usuario_info = get_usuario_info(current_user)
        empresa_info = get_empresa_info(db)
        pdf_buffer = create_report_pdf(sales_data, resumen_dict, "REPORTE DE VENTAS", periodo_pdf, "ventas", 
                                     usuario_info, empresa_info)
        
        headers = {
            'Content-Disposition': f'attachment; filename="reporte_ventas_{start_date_str}_a_{end_date_str}.pdf"'
        }
        return Response(content=pdf_buffer.getvalue(), media_type='application/pdf', headers=headers)

    # Calcular resumen
    total_ventas = sum(float(row['cantidad']) * float(row['precio_unitario']) for row in sales_data)
    cantidad_ventas = len(set(row['venta_id'] for row in sales_data))
    promedio_venta = total_ventas / cantidad_ventas if cantidad_ventas > 0 else 0
    
    # Producto más vendido
    productos_vendidos = {}
    categorias_vendidas = {}
    for row in sales_data:
        productos_vendidos[row['producto_nombre']] = productos_vendidos.get(row['producto_nombre'], 0) + float(row['cantidad'])
        categorias_vendidas[row['categoria_nombre']] = categorias_vendidas.get(row['categoria_nombre'], 0) + float(row['cantidad'])
    
    producto_mas_vendido = max(productos_vendidos, key=productos_vendidos.get) if productos_vendidos else None
    categoria_mas_vendida = max(categorias_vendidas, key=categorias_vendidas.get) if categorias_vendidas else None
    
    resumen = ResumenVentas(
        total_ventas=Decimal(str(total_ventas)),
        cantidad_ventas=cantidad_ventas,
        promedio_venta=Decimal(str(promedio_venta)),
        producto_mas_vendido=producto_mas_vendido,
        categoria_mas_vendida=categoria_mas_vendida
    )
    
    periodo_str = format_periodo_string(fecha_desde, fecha_hasta, None)
    
    # Crear items del reporte
    items = [ReporteVentaItem(**{**row, 'subtotal': Decimal(str(float(row['cantidad']) * float(row['precio_unitario'])))}) for row in sales_data]
    
    return ReporteVentasResponse(
        items=items,
        resumen=resumen,
        periodo=periodo_str
    )


@router.get("/compras", summary="Genera un reporte de compras detallado en JSON o PDF")
def get_purchases_report(
    fecha_desde: Optional[datetime] = Query(None, description="Fecha de inicio (YYYY-MM-DD)"),
    fecha_hasta: Optional[datetime] = Query(None, description="Fecha de fin (YYYY-MM-DD)"),
    periodo_tipo: Optional[str] = Query(None, description="Tipo de periodo: dia, mes, año"),
    proveedor_ids: Optional[List[int]] = Query(None, description="Lista de IDs de proveedores"),
    producto_ids: Optional[List[int]] = Query(None, description="Lista de IDs de productos"),
    categoria_ids: Optional[List[int]] = Query(None, description="Lista de IDs de categorías"),
    empleado_ids: Optional[List[int]] = Query(None, description="Lista de IDs de empleados"),
    formato: str = Query("json", description="Formato de salida: 'json' o 'pdf'"),
    db: Session = Depends(get_db),
    current_user: auth_utils.Usuario = Depends(auth_utils.require_menu_access("/reportes"))
):
    """
    Endpoint para obtener un reporte de compras con múltiples filtros.
    """
    # Calcular fechas según el periodo solo si se especifica un periodo válido
    if periodo_tipo and periodo_tipo in ["dia", "mes", "año"]:
        fecha_desde, fecha_hasta = get_periodo_fechas(periodo_tipo, fecha_desde, fecha_hasta)
    
    base_query = """
        SELECT
            c.compra_id,
            c.fecha_compra,
            COALESCE(p.nombre, e.razon_social, e.nombre_contacto) AS proveedor_nombre,
            COALESCE(p.ci, e.identificacion) AS proveedor_ruc,
            u_creador.nombre_usuario AS empleado_nombre,
            dc.cantidad,
            dc.precio_unitario,
            prod.nombre AS producto_nombre,
            cat.nombre_categoria AS categoria_nombre
        FROM
            compras c
        JOIN
            detalle_compras dc ON c.compra_id = dc.compra_id
        JOIN
            productos prod ON dc.producto_id = prod.producto_id
        JOIN
            categorias cat ON prod.categoria_id = cat.categoria_id
        JOIN
            proveedores prov ON c.proveedor_id = prov.proveedor_id
        LEFT JOIN
            personas p ON prov.persona_id = p.persona_id
        LEFT JOIN
            empresas e ON prov.empresa_id = e.empresa_id
        LEFT JOIN
            usuarios u_creador ON c.creado_por = u_creador.usuario_id
        WHERE
            c.estado != 'cancelado'
    """
    
    conditions = []
    params = {}

    if fecha_desde:
        conditions.append("c.fecha_compra >= :fecha_desde")
        params["fecha_desde"] = fecha_desde
    if fecha_hasta:
        conditions.append("c.fecha_compra <= :fecha_hasta")
        params["fecha_hasta"] = fecha_hasta
    
    if proveedor_ids:
        conditions.append("prov.proveedor_id IN :proveedor_ids")
        params["proveedor_ids"] = tuple(proveedor_ids)
    
    if empleado_ids:
        conditions.append("c.creado_por IN :empleado_ids")
        params["empleado_ids"] = tuple(empleado_ids)
    
    if producto_ids:
        conditions.append("prod.producto_id IN :producto_ids")
        params["producto_ids"] = tuple(producto_ids)
    
    if categoria_ids:
        conditions.append("cat.categoria_id IN :categoria_ids")
        params["categoria_ids"] = tuple(categoria_ids)

    if conditions:
        base_query += " AND " + " AND ".join(conditions)
    
    base_query += " ORDER BY c.fecha_compra DESC"

    result = db.execute(text(base_query), params)
    
    purchases_data = []
    for row in result:
        purchases_data.append({
            "compra_id": row.compra_id,
            "fecha_compra": row.fecha_compra.strftime('%Y-%m-%d %H:%M') if hasattr(row.fecha_compra, 'strftime') else str(row.fecha_compra),
            "proveedor_nombre": row.proveedor_nombre,
            "proveedor_ruc": row.proveedor_ruc,
            "empleado_nombre": row.empleado_nombre,
            "cantidad": row.cantidad,
            "precio_compra": row.precio_unitario,
            "producto_nombre": row.producto_nombre,
            "categoria_nombre": row.categoria_nombre,
        })

    if not purchases_data:
        raise HTTPException(status_code=404, detail="No se encontraron compras con los filtros aplicados.")

    # Calcular resumen
    total_compras = sum(float(row['cantidad']) * float(row['precio_compra']) for row in purchases_data)
    cantidad_compras = len(set(row['compra_id'] for row in purchases_data))
    promedio_compra = total_compras / cantidad_compras if cantidad_compras > 0 else 0
    
    # Proveedor más frecuente
    proveedores_frecuencia = {}
    categorias_compradas = {}
    for row in purchases_data:
        proveedores_frecuencia[row['proveedor_nombre']] = proveedores_frecuencia.get(row['proveedor_nombre'], 0) + 1
        categorias_compradas[row['categoria_nombre']] = categorias_compradas.get(row['categoria_nombre'], 0) + float(row['cantidad'])
    
    proveedor_mas_frecuente = max(proveedores_frecuencia, key=proveedores_frecuencia.get) if proveedores_frecuencia else None
    categoria_mas_comprada = max(categorias_compradas, key=categorias_compradas.get) if categorias_compradas else None

    if formato.lower() == "pdf":
        resumen_dict = {
            'total_compras': total_compras,
            'cantidad_compras': cantidad_compras,
            'promedio_compra': promedio_compra,
            'proveedor_mas_frecuente': proveedor_mas_frecuente or 'N/A',
            'categoria_mas_comprada': categoria_mas_comprada or 'N/A'
        }
        
        periodo_pdf = format_periodo_string(fecha_desde, fecha_hasta, periodo_tipo)
        usuario_info = get_usuario_info(current_user)
        empresa_info = get_empresa_info(db)
        pdf_buffer = create_report_pdf(purchases_data, resumen_dict, "REPORTE DE COMPRAS", periodo_pdf, "compras",
                                     usuario_info, empresa_info)
        
        start_date_str = fecha_desde.strftime('%Y-%m-%d') if fecha_desde else "Inicio"
        end_date_str = fecha_hasta.strftime('%Y-%m-%d') if fecha_hasta else "Fin"
        
        headers = {
            'Content-Disposition': f'attachment; filename="reporte_compras_{start_date_str}_a_{end_date_str}.pdf"'
        }
        return Response(content=pdf_buffer.getvalue(), media_type='application/pdf', headers=headers)

    resumen = ResumenCompras(
        total_compras=Decimal(str(total_compras)),
        cantidad_compras=cantidad_compras,
        promedio_compra=Decimal(str(promedio_compra)),
        proveedor_mas_frecuente=proveedor_mas_frecuente,
        categoria_mas_comprada=categoria_mas_comprada
    )
    
    periodo_str = format_periodo_string(fecha_desde, fecha_hasta, periodo_tipo)
    
    # Crear items del reporte
    items = [ReporteCompraItem(**{**row, 'subtotal': Decimal(str(float(row['cantidad']) * float(row['precio_compra'])))}) for row in purchases_data]
    
    return ReporteComprasResponse(
        items=items,
        resumen=resumen,
        periodo=periodo_str
    )


@router.get("/productos", summary="Genera un reporte de productos/inventario en JSON o PDF")
def get_products_report(
    categoria_ids: Optional[List[int]] = Query(None, description="Lista de IDs de categorías"),
    marca_ids: Optional[List[int]] = Query(None, description="Lista de IDs de marcas"),
    stock_minimo: Optional[bool] = Query(None, description="Solo productos con stock bajo"),
    sin_stock: Optional[bool] = Query(None, description="Solo productos sin stock"),
    formato: str = Query("json", description="Formato de salida: 'json' o 'pdf'"),
    db: Session = Depends(get_db),
    current_user: auth_utils.Usuario = Depends(auth_utils.require_menu_access("/reportes"))
):
    """
    Endpoint para obtener un reporte de productos/inventario.
    """
    
    base_query = """
        SELECT
            p.producto_id,
            p.codigo,
            p.nombre,
            p.stock,
            p.stock_minimo,
            p.precio_compra,
            p.precio_venta,
            p.estado,
            cat.nombre_categoria AS categoria_nombre,
            m.nombre_marca AS marca_nombre,
            um.nombre_unidad AS unidad_medida,
            COALESCE(ventas_totales.total_vendido, 0) AS total_vendido,
            COALESCE(compras_totales.total_comprado, 0) AS total_comprado
        FROM
            productos p
        JOIN
            categorias cat ON p.categoria_id = cat.categoria_id
        JOIN
            marcas m ON p.marca_id = m.marca_id
        JOIN
            unidades_medida um ON p.unidad_inventario_id = um.unidad_id
        LEFT JOIN (
            SELECT 
                dv.producto_id,
                SUM(dv.cantidad) AS total_vendido
            FROM detalle_ventas dv
            JOIN ventas v ON dv.venta_id = v.venta_id
            WHERE v.estado = 'activa'
            GROUP BY dv.producto_id
        ) ventas_totales ON p.producto_id = ventas_totales.producto_id
        LEFT JOIN (
            SELECT 
                dc.producto_id,
                SUM(dc.cantidad) AS total_comprado
            FROM detalle_compras dc
            JOIN compras c ON dc.compra_id = c.compra_id
            WHERE c.estado != 'cancelado'
            GROUP BY dc.producto_id
        ) compras_totales ON p.producto_id = compras_totales.producto_id
        WHERE
            p.estado = 'activo'
    """
    
    conditions = []
    params = {}
    
    if categoria_ids:
        conditions.append("cat.categoria_id IN :categoria_ids")
        params["categoria_ids"] = tuple(categoria_ids)
    
    if marca_ids:
        conditions.append("m.marca_id IN :marca_ids")
        params["marca_ids"] = tuple(marca_ids)
    
    if stock_minimo:
        conditions.append("p.stock <= p.stock_minimo")
    
    if sin_stock:
        conditions.append("p.stock = 0")

    if conditions:
        base_query += " AND " + " AND ".join(conditions)
    
    base_query += " ORDER BY p.nombre ASC"

    result = db.execute(text(base_query), params)
    
    products_data = []
    for row in result:
        margen = 0
        if float(row.precio_compra) > 0:
            margen = ((float(row.precio_venta) - float(row.precio_compra)) / float(row.precio_compra)) * 100
        
        products_data.append({
            "producto_id": row.producto_id,
            "codigo": row.codigo,
            "nombre": row.nombre,
            "categoria_nombre": row.categoria_nombre,
            "marca_nombre": row.marca_nombre,
            "stock_actual": row.stock,
            "stock_minimo": row.stock_minimo,
            "precio_compra": row.precio_compra,
            "precio_venta": row.precio_venta,
            "unidad_medida": row.unidad_medida,
            "estado": row.estado,
            "total_vendido": row.total_vendido or 0,
            "total_comprado": row.total_comprado or 0,
            "margen_ganancia": margen
        })

    if not products_data:
        raise HTTPException(status_code=404, detail="No se encontraron productos con los filtros aplicados.")

    # Calcular resumen
    total_productos = len(products_data)
    productos_con_stock = len([p for p in products_data if float(p['stock_actual']) > 0])
    productos_sin_stock = len([p for p in products_data if float(p['stock_actual']) == 0])
    productos_stock_bajo = len([p for p in products_data if float(p['stock_actual']) <= p['stock_minimo'] and float(p['stock_actual']) > 0])
    valor_inventario = sum(float(p['stock_actual']) * float(p['precio_compra']) for p in products_data)

    if formato.lower() == "pdf":
        resumen_dict = {
            'total_productos': total_productos,
            'productos_con_stock': productos_con_stock,
            'productos_sin_stock': productos_sin_stock,
            'productos_stock_bajo': productos_stock_bajo,
            'valor_inventario': valor_inventario
        }
        
        usuario_info = get_usuario_info(current_user)
        empresa_info = get_empresa_info(db)
        pdf_buffer = create_report_pdf(products_data, resumen_dict, "REPORTE DE INVENTARIO", "Estado actual del inventario", "productos",
                                     usuario_info, empresa_info)
        
        headers = {
            'Content-Disposition': f'attachment; filename="reporte_inventario_{datetime.now().strftime("%Y%m%d")}.pdf"'
        }
        return Response(content=pdf_buffer.getvalue(), media_type='application/pdf', headers=headers)

    resumen = ResumenProductos(
        total_productos=total_productos,
        productos_con_stock=productos_con_stock,
        productos_sin_stock=productos_sin_stock,
        productos_stock_bajo=productos_stock_bajo,
        valor_inventario=Decimal(str(valor_inventario))
    )
    
    # Crear items del reporte
    items = [ReporteProductoItem(**row) for row in products_data]
    
    return ReporteProductosResponse(
        items=items,
        resumen=resumen
    )
