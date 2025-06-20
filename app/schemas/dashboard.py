from pydantic import BaseModel
from typing import List, Optional
from datetime import date

class KpiCard(BaseModel):
    title: str
    value: str
    icon: Optional[str] = None
    change: Optional[str] = None # Ej: "+5.4%"

class SalesOverTimePoint(BaseModel):
    dia: date
    total_ventas: float

class TopProduct(BaseModel):
    producto: str
    ingresos_totales: float

class InventoryByCategory(BaseModel):
    categoria: str
    valor_inventario: float

class DashboardData(BaseModel):
    kpi_cards: List[KpiCard]
    sales_over_time: List[SalesOverTimePoint]
    top_products: List[TopProduct]
    inventory_by_category: List[InventoryByCategory]
    
