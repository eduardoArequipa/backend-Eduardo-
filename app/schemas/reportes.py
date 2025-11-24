from pydantic import BaseModel, Field
from typing import List, Optional, Literal
from datetime import datetime
from decimal import Decimal


class FiltroReporteBase(BaseModel):
    fecha_desde: Optional[datetime] = Field(None, description="Fecha de inicio del periodo")
    fecha_hasta: Optional[datetime] = Field(None, description="Fecha de fin del periodo")
    periodo_tipo: Optional[Literal["dia", "mes", "año"]] = Field(None, description="Tipo de periodo: día, mes o año")


class FiltroReporteVentas(FiltroReporteBase):
    producto_ids: Optional[List[int]] = Field(None, description="Lista de IDs de productos")
    categoria_ids: Optional[List[int]] = Field(None, description="Lista de IDs de categorías")
    empleado_ids: Optional[List[int]] = Field(None, description="Lista de IDs de empleados")
    metodo_pago_ids: Optional[List[int]] = Field(None, description="Lista de IDs de métodos de pago")


class FiltroReporteCompras(FiltroReporteBase):
    proveedor_ids: Optional[List[int]] = Field(None, description="Lista de IDs de proveedores")
    producto_ids: Optional[List[int]] = Field(None, description="Lista de IDs de productos")
    categoria_ids: Optional[List[int]] = Field(None, description="Lista de IDs de categorías")
    empleado_ids: Optional[List[int]] = Field(None, description="Lista de IDs de empleados")


class FiltroReporteProductos(BaseModel):
    categoria_ids: Optional[List[int]] = Field(None, description="Lista de IDs de categorías")
    marca_ids: Optional[List[int]] = Field(None, description="Lista de IDs de marcas")
    stock_minimo: Optional[bool] = Field(None, description="Solo productos con stock bajo")
    sin_stock: Optional[bool] = Field(None, description="Solo productos sin stock")


class ReporteVentaItem(BaseModel):
    venta_id: int
    fecha_venta: datetime
    cliente_nombre: Optional[str] = None
    cliente_apellido: Optional[str] = None
    vendedor_nombre: Optional[str] = None
    metodo_pago: Optional[str] = None
    producto_nombre: str
    categoria_nombre: str
    cantidad: Decimal
    precio_unitario: Decimal
    subtotal: Decimal


class ReporteCompraItem(BaseModel):
    compra_id: int
    fecha_compra: datetime
    proveedor_nombre: str
    proveedor_ruc: Optional[str] = None
    empleado_nombre: Optional[str] = None
    producto_nombre: str
    categoria_nombre: str
    cantidad: Decimal
    precio_compra: Decimal
    subtotal: Decimal


class ReporteProductoItem(BaseModel):
    producto_id: int
    codigo: str
    nombre: str
    categoria_nombre: str
    marca_nombre: str
    stock_actual: Decimal
    stock_minimo: Decimal
    precio_compra: Decimal
    precio_venta: Decimal
    unidad_medida: str
    estado: str
    total_vendido: Optional[Decimal] = Field(default=0, description="Cantidad total vendida")
    total_comprado: Optional[Decimal] = Field(default=0, description="Cantidad total comprada")
    margen_ganancia: Optional[Decimal] = Field(default=0, description="Margen de ganancia calculado")


class ResumenVentas(BaseModel):
    total_ventas: Decimal
    cantidad_ventas: int
    promedio_venta: Decimal
    producto_mas_vendido: Optional[str] = None
    categoria_mas_vendida: Optional[str] = None


class ResumenCompras(BaseModel):
    total_compras: Decimal
    cantidad_compras: int
    promedio_compra: Decimal
    proveedor_mas_frecuente: Optional[str] = None
    categoria_mas_comprada: Optional[str] = None


class ResumenProductos(BaseModel):
    total_productos: int
    productos_con_stock: int
    productos_sin_stock: int
    productos_stock_bajo: int
    valor_inventario: Decimal


class ReporteVentasResponse(BaseModel):
    items: List[ReporteVentaItem]
    resumen: ResumenVentas
    periodo: str


class ReporteComprasResponse(BaseModel):
    items: List[ReporteCompraItem]
    resumen: ResumenCompras
    periodo: str


class ReporteProductosResponse(BaseModel):
    items: List[ReporteProductoItem]
    resumen: ResumenProductos