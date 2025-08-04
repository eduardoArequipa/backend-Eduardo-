from pydantic import BaseModel
from typing import List, Optional
from datetime import date

# --- Esquemas existentes ---

class KpiCard(BaseModel):
    title: str
    value: str
    icon: Optional[str] = None

class SalesDataPoint(BaseModel):
    period: str  # Puede ser '2023-10-27', '2023-10' (Oct), '2023'
    total: float

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
    
