from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import text
from typing import List
from datetime import datetime, timedelta

from ..database import get_db
from app.schemas.dashboard import DashboardData,KpiCard

router = APIRouter(
    prefix="/dashboard",
    tags=["Dashboard"]
)

@router.get("/", response_model=DashboardData)
def get_dashboard_data(db: Session = Depends(get_db)):
    # --- 1. KPIs Cards ---
    # Ventas del mes actual
    start_of_month = datetime.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    query_ventas_mes = text("SELECT COALESCE(SUM(total), 0) FROM ventas WHERE fecha_venta >= :start_date AND estado = 'activa'")
    ventas_mes = db.execute(query_ventas_mes, {"start_date": start_of_month}).scalar()

    # Ganancia Bruta del mes (simplificado)
    # Nota: Una consulta más precisa requeriría joins complejos. Para empezar, podemos hacer una estimación.
    # O, mejor, podrías crear una vista para esto. Por ahora, un placeholder:
    query_ganancia = text("""
        SELECT COALESCE(SUM(dv.cantidad * (dv.precio_unitario - p.precio_compra)), 0)
        FROM detalle_ventas dv
        JOIN ventas v ON v.venta_id = dv.venta_id
        JOIN productos p ON p.producto_id = dv.producto_id
        WHERE v.fecha_venta >= :start_date AND v.estado = 'activa'
    """)
    ganancia_mes = db.execute(query_ganancia, {"start_date": start_of_month}).scalar()

    # Productos con Stock Crítico
    stock_critico_count = db.execute(text("SELECT COUNT(*) FROM stock_critico")).scalar()

    kpi_cards = [
        KpiCard(title="Ventas del Mes", value=f"Bs. {ventas_mes:,.2f}"),
        KpiCard(title="Ganancia Bruta (Mes)", value=f"Bs. {max(ganancia_mes, 0):,.2f}"),
        KpiCard(title="Alertas de Stock", value=str(stock_critico_count)),
    ]

    # --- 2. Gráficos ---
    # Ventas en los últimos 30 días
    thirty_days_ago = datetime.now() - timedelta(days=30)
    query_sales_trend = text("SELECT dia, total_ventas FROM ventas_diarias WHERE dia >= :start_date ORDER BY dia ASC")
    sales_over_time_data = db.execute(query_sales_trend, {"start_date": thirty_days_ago}).fetchall()
    sales_over_time = [{"dia": row[0], "total_ventas": row[1]} for row in sales_over_time_data]


    # Top 5 Productos más vendidos
    query_top_products = text("SELECT producto, ingresos_totales FROM ventas_por_producto ORDER BY ingresos_totales DESC LIMIT 5")
    top_products_data = db.execute(query_top_products).fetchall()
    top_products = [{"producto": row[0], "ingresos_totales": row[1]} for row in top_products_data]

    # Valor de inventario por categoría
    query_inv_category = text("SELECT categoria, valor_inventario FROM resumen_inventario_por_categoria")
    inv_category_data = db.execute(query_inv_category).fetchall()
    inventory_by_category = [{"categoria": row[0], "valor_inventario": row[1]} for row in inv_category_data]


    return DashboardData(
        kpi_cards=kpi_cards,
        sales_over_time=sales_over_time,
        top_products=top_products,
        inventory_by_category=inventory_by_category,
    )