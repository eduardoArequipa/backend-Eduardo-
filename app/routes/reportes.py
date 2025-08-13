from fastapi import APIRouter, Depends, Query, HTTPException, Response
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func, and_, text # Importar text
from typing import List, Optional
from datetime import datetime
import io

# Importaciones de ReportLab
from reportlab.lib.pagesizes import letter, landscape
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib import colors

# Importaciones de la aplicación
from ..database import get_db
from .. import auth
from ..models.venta import Venta
from ..models.detalle_venta import DetalleVenta
from ..models.producto import Producto
from ..models.persona import Persona
from ..models.usuario import Usuario
from ..models.categoria import Categoria
from .. import auth as auth_utils 


router = APIRouter(
    prefix="/reportes",
    tags=["reportes"]
)

# Roles que pueden acceder a este endpoint
ROLES_CAN_ACCESS_REPORTS = ["Administrador", "Empleado"]

def create_sales_report_pdf(sales_data: list, start_date: str, end_date: str):
    """
    Genera un reporte de ventas en formato PDF usando ReportLab.
    """
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=landscape(letter))
    
    styles = getSampleStyleSheet()
    elements = []

    # Título
    title = Paragraph(f"Reporte de Ventas Detallado", styles['h1'])
    elements.append(title)
    
    # Rango de fechas
    date_range = Paragraph(f"Período: {start_date} al {end_date}", styles['h3'])
    elements.append(date_range)
    elements.append(Spacer(1, 12))

    # Definir encabezados de la tabla
    headers = [
        "ID Venta", "Fecha", "Cliente", "Vendido por", 
        "Producto", "Categoría", "Cantidad", "Precio Unit.", "Subtotal"
    ]
    
    # Preparar los datos para la tabla
    table_data = [headers]
    total_general = 0

    for row in sales_data: # Ahora sales_data es una lista de diccionarios
        cliente_nombre = f"{row['cliente_nombre']} {row['cliente_apellido'] or ''}".strip() if row['cliente_nombre'] else "N/A"
        vendedor_nombre = row['vendedor_nombre'] if row['vendedor_nombre'] else "N/A"
        
        subtotal = row['cantidad'] * row['precio_unitario']
        total_general += subtotal
        
        table_data.append([
            row['venta_id'],
            row['fecha_venta'],
            cliente_nombre,
            vendedor_nombre,
            row['producto_nombre'],
            row['categoria_nombre'],
            f"{row['cantidad']:.2f}",
            f"{row['precio_unitario']:.2f}",
            f"{subtotal:.2f}"
        ])

    # Añadir fila de total general
    total_row = ["", "", "", "", "", "", "", "Total General:", f"{total_general:.2f}"]
    table_data.append(total_row)

    # Crear la tabla y aplicar estilos
    table = Table(table_data)
    style = TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, 1), (-1, -2), colors.beige),
        ('GRID', (0, 0), (-1, -1), 1, colors.black),
        # Estilo para la fila de total
        ('BACKGROUND', (0, -1), (-1, -1), colors.lightgrey),
        ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
        ('ALIGN', (7, -1), (8, -1), 'RIGHT'),
    ])
    table.setStyle(style)
    
    elements.append(table)
    
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
        
        pdf_buffer = create_sales_report_pdf(sales_data, start_date_str, end_date_str)
        
        headers = {
            'Content-Disposition': f'attachment; filename="reporte_ventas_{start_date_str}_a_{end_date_str}.pdf"'
        }
        return Response(content=pdf_buffer.getvalue(), media_type='application/pdf', headers=headers)

    # Por defecto, devuelve JSON (puedes ajustar el esquema de respuesta si es necesario)
    return sales_data
