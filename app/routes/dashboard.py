from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import text
from typing import List
from datetime import datetime, timedelta

from ..database import get_db
from app.schemas.dashboard import (
    DashboardData, KpiCard, SalesDataPoint, TopSellingProduct,
    InventoryByCategory, PurchaseStats, TopSupplier, TopPurchasedProduct,
    LowStockProduct
)

router = APIRouter(
    prefix="/dashboard",
    tags=["Dashboard"]
)

@router.get("/", response_model=DashboardData)
def get_dashboard_data(db: Session = Depends(get_db)):

    # --- 1. KPIs ---
    start_of_month = datetime.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    query_ventas_mes = text("SELECT COALESCE(SUM(total), 0) FROM ventas WHERE fecha_venta >= :start_date AND estado = 'activa'")
    ventas_mes = db.execute(query_ventas_mes, {"start_date": start_of_month}).scalar()

    query_ganancia = text("""
        SELECT COALESCE(SUM(dv.cantidad * (dv.precio_unitario - p.precio_compra)), 0)
        FROM detalle_ventas dv
        JOIN ventas v ON v.venta_id = dv.venta_id
        JOIN productos p ON p.producto_id = dv.producto_id
        WHERE v.fecha_venta >= :start_date AND v.estado = 'activa'
    """)
    ganancia_mes = db.execute(query_ganancia, {"start_date": start_of_month}).scalar()

    query_stock_critico = text("SELECT COUNT(*) FROM productos WHERE stock <= stock_minimo AND estado = 'activo'")
    stock_critico_count = db.execute(query_stock_critico).scalar()

    kpi_cards = [
        KpiCard(title="Ventas del Mes", value=f"Bs. {ventas_mes:,.2f}"),
        KpiCard(title="Ganancia Bruta (Mes)", value=f"Bs. {max(ganancia_mes, 0):,.2f}"),
        KpiCard(title="Alertas de Stock", value=str(stock_critico_count)),
    ]

    # --- 2. Estadísticas de Ventas (Consultas Directas) ---
    thirty_days_ago = datetime.now() - timedelta(days=30)
    query_sales_daily = text("""
        SELECT DATE(fecha_venta) as dia, SUM(total) as total_ventas
        FROM ventas
        WHERE fecha_venta >= :start_date AND estado = 'activa'
        GROUP BY dia ORDER BY dia ASC
    """)
    sales_daily_data = db.execute(query_sales_daily, {"start_date": thirty_days_ago}).fetchall()
    sales_daily = [SalesDataPoint(period=row[0].isoformat(), total=row[1]) for row in sales_daily_data]

    query_sales_monthly = text("""
        SELECT TO_CHAR(fecha_venta, 'YYYY-MM') as anio_mes, SUM(total) as total_ventas
        FROM ventas WHERE estado = 'activa'
        GROUP BY anio_mes ORDER BY anio_mes DESC LIMIT 12
    """)
    sales_monthly_data = db.execute(query_sales_monthly).fetchall()
    sales_monthly = [SalesDataPoint(period=row[0], total=row[1]) for row in sales_monthly_data]

    query_sales_yearly = text("""
        SELECT EXTRACT(YEAR FROM fecha_venta)::INTEGER as anio, SUM(total) as total_ventas
        FROM ventas WHERE estado = 'activa'
        GROUP BY anio ORDER BY anio DESC LIMIT 5
    """)
    sales_yearly_data = db.execute(query_sales_yearly).fetchall()
    sales_yearly = [SalesDataPoint(period=str(row[0]), total=row[1]) for row in sales_yearly_data]

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

    return DashboardData(
        kpi_cards=kpi_cards,
        sales_daily=sales_daily,
        sales_monthly=sales_monthly,
        sales_yearly=sales_yearly,
        top_selling_products=top_selling_products,
        inventory_by_category=inventory_by_category,
        purchase_stats=purchase_stats,
        low_stock_products=low_stock_products,
        total_inventory_value=total_inventory_value
    )