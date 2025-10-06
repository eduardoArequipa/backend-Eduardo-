from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import text
from typing import List, Optional
from datetime import datetime, timedelta, date

from ..database import get_db
from app.schemas.dashboard import (
    DashboardData, KpiCard, SalesDataPoint, TopSellingProduct,
    InventoryByCategory, PurchaseStats, TopSupplier, TopPurchasedProduct,
    LowStockProduct, DrillDownData, DrillDownDetail, ProductDetail
)
from .. import auth as auth_utils

router = APIRouter(
    prefix="/dashboard",
    tags=["Dashboard"]
)

@router.get("/", response_model=DashboardData)
def get_dashboard_data(
    db: Session = Depends(get_db),
    start_date: Optional[date] = Query(None, description="Fecha de inicio para filtros"),
    end_date: Optional[date] = Query(None, description="Fecha de fin para filtros"),
    category: Optional[str] = Query(None, description="Filtrar por categoría"),
    supplier: Optional[str] = Query(None, description="Filtrar por proveedor"),
    compare_with_previous: Optional[bool] = Query(False, description="Comparar con período anterior")
):
    current_user: auth_utils.Usuario = Depends(auth_utils.require_menu_access("/compras")) # Verificar acceso al menú de categorías

    # --- Construir filtros dinámicos ---
    date_filter = ""
    date_params = {}

    if start_date and end_date:
        date_filter = " AND v.fecha_venta BETWEEN :start_date AND :end_date"
        date_params = {"start_date": start_date, "end_date": end_date}
    elif start_date:
        date_filter = " AND v.fecha_venta >= :start_date"
        date_params = {"start_date": start_date}
    elif end_date:
        date_filter = " AND v.fecha_venta <= :end_date"
        date_params = {"end_date": end_date}

    category_filter = ""
    category_params = {}
    if category:
        category_filter = " AND c.nombre_categoria = :category"
        category_params = {"category": category}

    supplier_filter = ""
    supplier_params = {}
    if supplier:
        supplier_filter = " AND (COALESCE(pr.nombre, e.razon_social) = :supplier)"
        supplier_params = {"supplier": supplier}

    # --- 1. KPIs ---
    if start_date and end_date:
        kpi_start_date = start_date
    else:
        kpi_start_date = datetime.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    query_ventas_mes = text(f"SELECT COALESCE(SUM(v.total), 0) FROM ventas v WHERE v.fecha_venta >= :kpi_start_date AND v.estado = 'activa'{date_filter}")
    kpi_params = {"kpi_start_date": kpi_start_date, **date_params}
    ventas_mes = db.execute(query_ventas_mes, kpi_params).scalar()

    query_ganancia = text(f"""
        SELECT COALESCE(SUM(dv.cantidad * (dv.precio_unitario - p.precio_compra)), 0)
        FROM detalle_ventas dv
        JOIN ventas v ON v.venta_id = dv.venta_id
        JOIN productos p ON p.producto_id = dv.producto_id
        {f"JOIN categorias c ON p.categoria_id = c.categoria_id" if category else ""}
        WHERE v.fecha_venta >= :kpi_start_date AND v.estado = 'activa'{date_filter}{category_filter}
    """)
    ganancia_params = {**kpi_params, **category_params}
    ganancia_mes = db.execute(query_ganancia, ganancia_params).scalar()

    query_stock_critico = text("SELECT COUNT(*) FROM productos WHERE stock <= stock_minimo AND estado = 'activo'")
    stock_critico_count = db.execute(query_stock_critico).scalar()

    kpi_cards = [
        KpiCard(title="Ventas del Mes", value=f"Bs. {ventas_mes:,.2f}"),
        KpiCard(title="Ganancia Bruta (Mes)", value=f"Bs. {max(ganancia_mes, 0):,.2f}"),
        KpiCard(title="Alertas de Stock", value=str(stock_critico_count)),
    ]

    # --- 2. Estadísticas de Ventas con filtros ---
    default_start = datetime.now() - timedelta(days=30)
    sales_start_date = start_date if start_date else default_start
    sales_end_date = end_date if end_date else datetime.now().date()

    # Query mejorada para ventas diarias con conteo de transacciones
    query_sales_daily = text(f"""
        SELECT
            DATE(v.fecha_venta) as dia,
            SUM(v.total) as total_ventas,
            COUNT(v.venta_id) as num_transacciones
        FROM ventas v
        {f"JOIN detalle_ventas dv ON v.venta_id = dv.venta_id JOIN productos p ON dv.producto_id = p.producto_id JOIN categorias c ON p.categoria_id = c.categoria_id" if category else ""}
        WHERE v.fecha_venta BETWEEN :sales_start AND :sales_end AND v.estado = 'activa'{category_filter}
        GROUP BY dia ORDER BY dia ASC
    """)

    sales_params = {"sales_start": sales_start_date, "sales_end": sales_end_date, **category_params}
    sales_daily_data = db.execute(query_sales_daily, sales_params).fetchall()

    sales_daily = []
    for row in sales_daily_data:
        data_point = SalesDataPoint(
            period=row[0].isoformat(),
            total=row[1],
            quantity=row[2] if len(row) > 2 else None
        )

        # Si se pidió comparación, calcular período anterior
        if compare_with_previous:
            prev_date = row[0] - timedelta(days=30)  # 30 días antes
            query_prev = text(f"""
                SELECT COALESCE(SUM(v.total), 0)
                FROM ventas v
                {f"JOIN detalle_ventas dv ON v.venta_id = dv.venta_id JOIN productos p ON dv.producto_id = p.producto_id JOIN categorias c ON p.categoria_id = c.categoria_id" if category else ""}
                WHERE DATE(v.fecha_venta) = :prev_date AND v.estado = 'activa'{category_filter}
            """)
            prev_params = {"prev_date": prev_date, **category_params}
            prev_total = db.execute(query_prev, prev_params).scalar()
            data_point.previousPeriodTotal = prev_total

        sales_daily.append(data_point)

    # Sales mensuales con filtros
    query_sales_monthly = text(f"""
        SELECT
            TO_CHAR(v.fecha_venta, 'YYYY-MM') as anio_mes,
            SUM(v.total) as total_ventas,
            COUNT(v.venta_id) as num_transacciones
        FROM ventas v
        {f"JOIN detalle_ventas dv ON v.venta_id = dv.venta_id JOIN productos p ON dv.producto_id = p.producto_id JOIN categorias c ON p.categoria_id = c.categoria_id" if category else ""}
        WHERE v.estado = 'activa'{date_filter.replace('v.fecha_venta BETWEEN', 'v.fecha_venta BETWEEN') if date_filter else ''}{category_filter}
        GROUP BY anio_mes ORDER BY anio_mes DESC LIMIT 12
    """)
    monthly_params = {**date_params, **category_params}
    sales_monthly_data = db.execute(query_sales_monthly, monthly_params).fetchall()
    sales_monthly = [SalesDataPoint(period=row[0], total=row[1], quantity=row[2] if len(row) > 2 else None) for row in sales_monthly_data]

    # Sales anuales con filtros
    query_sales_yearly = text(f"""
        SELECT
            EXTRACT(YEAR FROM v.fecha_venta)::INTEGER as anio,
            SUM(v.total) as total_ventas,
            COUNT(v.venta_id) as num_transacciones
        FROM ventas v
        {f"JOIN detalle_ventas dv ON v.venta_id = dv.venta_id JOIN productos p ON dv.producto_id = p.producto_id JOIN categorias c ON p.categoria_id = c.categoria_id" if category else ""}
        WHERE v.estado = 'activa'{date_filter.replace('v.fecha_venta BETWEEN', 'v.fecha_venta BETWEEN') if date_filter else ''}{category_filter}
        GROUP BY anio ORDER BY anio DESC LIMIT 5
    """)
    yearly_params = {**date_params, **category_params}
    sales_yearly_data = db.execute(query_sales_yearly, yearly_params).fetchall()
    sales_yearly = [SalesDataPoint(period=str(row[0]), total=row[1], quantity=row[2] if len(row) > 2 else None) for row in sales_yearly_data]

    # --- 3. Estadísticas de Productos (Consultas Corregidas) ---
    query_top_products = text("""
        SELECT p.nombre, SUM(dv.precio_unitario * dv.cantidad) as ingresos_totales
        FROM detalle_ventas dv
        JOIN productos p ON dv.producto_id = p.producto_id
        JOIN ventas v ON dv.venta_id = v.venta_id
        WHERE v.estado = 'activa'
        GROUP BY p.nombre ORDER BY ingresos_totales DESC LIMIT 5
    """)
    top_products_data = db.execute(query_top_products).fetchall()
    top_selling_products = [TopSellingProduct(producto=row[0], ingresos_totales=row[1]) for row in top_products_data]

    query_inv_category = text("""
        SELECT c.nombre_categoria, COALESCE(SUM(p.stock * p.precio_compra), 0) as valor_inventario
        FROM productos p
        JOIN categorias c ON p.categoria_id = c.categoria_id
        WHERE p.estado = 'activo'
        GROUP BY c.nombre_categoria ORDER BY valor_inventario DESC
    """)
    inv_category_data = db.execute(query_inv_category).fetchall()
    inventory_by_category = [InventoryByCategory(categoria=row[0], valor_inventario=row[1]) for row in inv_category_data]
    
    total_inventory_value = sum(item.valor_inventario for item in inventory_by_category)

    query_low_stock = text("SELECT producto_id, nombre, stock, stock_minimo FROM productos WHERE stock <= stock_minimo AND estado = 'activo' ORDER BY stock ASC LIMIT 10")
    low_stock_data = db.execute(query_low_stock).fetchall()
    low_stock_products = [LowStockProduct(producto_id=r[0], nombre=r[1], stock=r[2], stock_minimo=r[3]) for r in low_stock_data]

    # --- 4. Estadísticas de Compras (Consulta Corregida) ---
    query_top_suppliers = text("""
        SELECT 
            COALESCE(pr.nombre, e.razon_social) as proveedor_nombre,
            SUM(c.total) as total_compras
        FROM compras c
        JOIN proveedores p ON c.proveedor_id = p.proveedor_id
        LEFT JOIN personas pr ON p.persona_id = pr.persona_id
        LEFT JOIN empresas e ON p.empresa_id = e.empresa_id
        WHERE c.estado = 'completada'
        GROUP BY proveedor_nombre
        ORDER BY total_compras DESC
        LIMIT 5
    """)
    top_suppliers_data = db.execute(query_top_suppliers).fetchall()
    top_suppliers = [TopSupplier(proveedor=row[0], total_compras=row[1]) for row in top_suppliers_data]

    query_top_purchased = text("""
        SELECT p.nombre, SUM(dc.cantidad) as cantidad_comprada
        FROM detalle_compras dc
        JOIN productos p ON dc.producto_id = p.producto_id
        JOIN compras c ON dc.compra_id = c.compra_id
        WHERE c.estado = 'completada'
        GROUP BY p.nombre
        ORDER BY cantidad_comprada DESC
        LIMIT 5
    """)
    top_purchased_data = db.execute(query_top_purchased).fetchall()
    top_purchased_products = [TopPurchasedProduct(producto=row[0], cantidad_comprada=row[1]) for row in top_purchased_data]

    purchase_stats = PurchaseStats(
        top_suppliers=top_suppliers,
        top_purchased_products=top_purchased_products
    )

    # --- Obtener listas para filtros ---
    query_categories = text("SELECT DISTINCT nombre_categoria FROM categorias WHERE estado = 'activo' ORDER BY nombre_categoria")
    categories_data = db.execute(query_categories).fetchall()
    available_categories = [row[0] for row in categories_data]

    query_suppliers = text("""
        SELECT DISTINCT COALESCE(pr.nombre, e.razon_social) as proveedor_nombre
        FROM proveedores p
        LEFT JOIN personas pr ON p.persona_id = pr.persona_id
        LEFT JOIN empresas e ON p.empresa_id = e.empresa_id
        WHERE p.estado = 'activo'
        ORDER BY proveedor_nombre
    """)
    suppliers_data = db.execute(query_suppliers).fetchall()
    available_suppliers = [row[0] for row in suppliers_data if row[0]]

    return DashboardData(
        kpi_cards=kpi_cards,
        sales_daily=sales_daily,
        sales_monthly=sales_monthly,
        sales_yearly=sales_yearly,
        top_selling_products=top_selling_products,
        inventory_by_category=inventory_by_category,
        purchase_stats=purchase_stats,
        low_stock_products=low_stock_products,
        total_inventory_value=total_inventory_value,
        available_categories=available_categories,
        available_suppliers=available_suppliers
    )


@router.get("/drill-down/", response_model=DrillDownData)
def get_drill_down_data(
    period: str = Query(..., description="Período para drill-down (ej: '2024-01', '2024-01-15')"),
    type: str = Query("sales", description="Tipo de drill-down: 'sales' o 'products'"),
    db: Session = Depends(get_db)
):
    """
    Endpoint para obtener datos detallados de un período específico
    """
    current_user: auth_utils.Usuario = Depends(auth_utils.require_menu_access("/compras"))

    if type == "sales":
        # Determinar si es drill-down diario, mensual o anual
        if len(period) == 10:  # Formato YYYY-MM-DD
            # Drill-down por horas del día
            query_details = text("""
                SELECT
                    TO_CHAR(fecha_venta, 'HH24:00') as hora,
                    SUM(total) as amount,
                    COUNT(venta_id) as transactions
                FROM ventas
                WHERE DATE(fecha_venta) = :period_date AND estado = 'activa'
                GROUP BY hora
                ORDER BY hora
            """)
            details_data = db.execute(query_details, {"period_date": period}).fetchall()
            details = [
                DrillDownDetail(
                    date=f"{period} {row[0]}",
                    amount=float(row[1]),
                    transactions=int(row[2])
                ) for row in details_data
            ]

        elif len(period) == 7:  # Formato YYYY-MM
            # Drill-down por días del mes
            query_details = text("""
                SELECT
                    DATE(fecha_venta) as dia,
                    SUM(total) as amount,
                    COUNT(venta_id) as transactions
                FROM ventas
                WHERE TO_CHAR(fecha_venta, 'YYYY-MM') = :period_month AND estado = 'activa'
                GROUP BY dia
                ORDER BY dia
            """)
            details_data = db.execute(query_details, {"period_month": period}).fetchall()
            details = [
                DrillDownDetail(
                    date=row[0].isoformat(),
                    amount=float(row[1]),
                    transactions=int(row[2])
                ) for row in details_data
            ]

        else:  # Formato YYYY (año)
            # Drill-down por meses del año
            query_details = text("""
                SELECT
                    TO_CHAR(fecha_venta, 'YYYY-MM') as mes,
                    SUM(total) as amount,
                    COUNT(venta_id) as transactions
                FROM ventas
                WHERE EXTRACT(YEAR FROM fecha_venta) = :period_year AND estado = 'activa'
                GROUP BY mes
                ORDER BY mes
            """)
            details_data = db.execute(query_details, {"period_year": int(period)}).fetchall()
            details = [
                DrillDownDetail(
                    date=row[0],
                    amount=float(row[1]),
                    transactions=int(row[2])
                ) for row in details_data
            ]

        return DrillDownData(period=period, details=details)

    else:
        # Para productos u otros tipos, retornar datos vacíos por ahora
        return DrillDownData(period=period, details=[])


@router.get("/product/{product_name}/", response_model=ProductDetail)
def get_product_detail(
    product_name: str,
    db: Session = Depends(get_db),
    current_user: auth_utils.Usuario = Depends(auth_utils.require_menu_access("/dashboard"))
):
    """
    Endpoint para obtener detalles completos de un producto específico
    """
    try:
        from urllib.parse import unquote
        from fastapi import HTTPException
        import logging

        # URL decode el nombre del producto
        product_name = unquote(product_name)
        logging.info(f"Buscando detalles para producto: {product_name}")

        # Query principal para obtener datos del producto
        query_product = text("""
            SELECT
                p.producto_id,
                p.nombre,
                c.nombre_categoria as categoria,
                m.nombre_marca as marca,
                p.stock as stock_actual,
                p.stock_minimo,
                p.precio_venta,
                p.precio_compra,
                p.estado,
                CASE
                    WHEN p.precio_compra > 0 THEN
                        ROUND(((p.precio_venta - p.precio_compra) / p.precio_compra * 100)::numeric, 2)
                    ELSE 0
                END as margen_ganancia
            FROM productos p
            LEFT JOIN categorias c ON p.categoria_id = c.categoria_id
            LEFT JOIN marcas m ON p.marca_id = m.marca_id
            WHERE p.nombre = :product_name AND p.estado = 'activo'
            LIMIT 1
        """)

        product_data = db.execute(query_product, {"product_name": product_name}).fetchone()

        if not product_data:
            logging.warning(f"Producto no encontrado: {product_name}")
            raise HTTPException(status_code=404, detail="Producto no encontrado")

        # Query para obtener ingresos totales y unidades vendidas
        query_sales = text("""
            SELECT
                COALESCE(SUM(dv.precio_unitario * dv.cantidad), 0) as ingresos_totales,
                COALESCE(SUM(dv.cantidad), 0) as unidades_vendidas
            FROM detalle_ventas dv
            JOIN productos p ON dv.producto_id = p.producto_id
            JOIN ventas v ON dv.venta_id = v.venta_id
            WHERE p.nombre = :product_name AND v.estado = 'activa'
        """)

        sales_data = db.execute(query_sales, {"product_name": product_name}).fetchone()

        # Query para obtener la fecha de la última venta
        query_last_sale = text("""
            SELECT DATE(v.fecha_venta) as ultima_venta
            FROM detalle_ventas dv
            JOIN productos p ON dv.producto_id = p.producto_id
            JOIN ventas v ON dv.venta_id = v.venta_id
            WHERE p.nombre = :product_name AND v.estado = 'activa'
            ORDER BY v.fecha_venta DESC
            LIMIT 1
        """)

        last_sale_data = db.execute(query_last_sale, {"product_name": product_name}).fetchone()

        # Query para obtener el proveedor principal
        query_main_supplier = text("""
            SELECT COALESCE(pr.nombre, e.razon_social) as proveedor_principal
            FROM detalle_compras dc
            JOIN productos p ON dc.producto_id = p.producto_id
            JOIN compras c ON dc.compra_id = c.compra_id
            JOIN proveedores prov ON c.proveedor_id = prov.proveedor_id
            LEFT JOIN personas pr ON prov.persona_id = pr.persona_id
            LEFT JOIN empresas e ON prov.empresa_id = e.empresa_id
            WHERE p.nombre = :product_name AND c.estado = 'completada'
            GROUP BY COALESCE(pr.nombre, e.razon_social)
            ORDER BY SUM(dc.cantidad) DESC
            LIMIT 1
        """)

        supplier_data = db.execute(query_main_supplier, {"product_name": product_name}).fetchone()

        # Construir respuesta
        return ProductDetail(
            producto_id=product_data[0],
            nombre=product_data[1],
            categoria=product_data[2] or "Sin categoría",
            marca=product_data[3] or None,
            stock_actual=product_data[4],
            stock_minimo=product_data[5] or 0,
            precio_venta=float(product_data[6]),
            precio_compra=float(product_data[7]),
            margen_ganancia=float(product_data[9]),
            estado=product_data[8],
            ingresos_totales=float(sales_data[0]) if sales_data else 0,
            unidades_vendidas=int(sales_data[1]) if sales_data else 0,
            ultima_venta=last_sale_data[0].isoformat() if last_sale_data and last_sale_data[0] else None,
            proveedor_principal=supplier_data[0] if supplier_data and supplier_data[0] else None
        )

    except Exception as e:
        logging.error(f"Error al obtener detalles del producto {product_name}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error interno del servidor: {str(e)}")