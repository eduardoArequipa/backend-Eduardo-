from pydantic import BaseModel
from typing import List, Optional
from datetime import date, datetime

# --- Esquemas existentes ---

class KpiCard(BaseModel):
    title: str
    value: str
    icon: Optional[str] = None

class SalesDataPoint(BaseModel):
    period: str  # Puede ser '2023-10-27', '2023-10' (Oct), '2023'
    total: float
    quantity: Optional[int] = None  # Para tooltips mejorados
    previousPeriodTotal: Optional[float] = None  # Para comparación

class TopSellingProduct(BaseModel):
    producto: str
    ingresos_totales: float

class InventoryByCategory(BaseModel):
    categoria: str
    valor_inventario: float

# --- Nuevos esquemas ---

class TopSupplier(BaseModel):
    proveedor: str
    total_compras: float

class TopPurchasedProduct(BaseModel):
    producto: str
    cantidad_comprada: float

class LowStockProduct(BaseModel):
    producto_id: int
    nombre: str
    stock: int
    stock_minimo: Optional[int]

class PurchaseStats(BaseModel):
    top_suppliers: List[TopSupplier]
    top_purchased_products: List[TopPurchasedProduct]

# --- Esquema principal ---

# --- Esquemas para filtros y drill-down ---

class DashboardFilters(BaseModel):
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    category: Optional[str] = None
    supplier: Optional[str] = None
    compare_with_previous: Optional[bool] = False

class DrillDownDetail(BaseModel):
    date: str
    amount: float
    transactions: int

class DrillDownData(BaseModel):
    period: str
    details: List[DrillDownDetail]

class ProductDetail(BaseModel):
    producto_id: int
    nombre: str
    categoria: str
    marca: Optional[str] = None
    stock_actual: int
    stock_minimo: int
    precio_venta: float
    precio_compra: float
    margen_ganancia: float  # Calculado como porcentaje
    ingresos_totales: float
    unidades_vendidas: int
    ultima_venta: Optional[str] = None  # Fecha de última venta
    proveedor_principal: Optional[str] = None
    estado: str

class DashboardData(BaseModel):
    kpi_cards: List[KpiCard]
    sales_daily: List[SalesDataPoint]
    sales_monthly: List[SalesDataPoint]
    sales_yearly: List[SalesDataPoint]
    top_selling_products: List[TopSellingProduct]
    inventory_by_category: List[InventoryByCategory]
    purchase_stats: PurchaseStats
    low_stock_products: List[LowStockProduct]
    total_inventory_value: float
    available_categories: List[str]  # Para filtros
    available_suppliers: List[str]   # Para filtros
