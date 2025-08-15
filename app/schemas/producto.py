from typing import Optional, List
from pydantic import BaseModel, ConfigDict, Field
from decimal import Decimal
from .categoria import CategoriaNested
from .usuario import UsuarioAudit
from .unidad_medida import UnidadMedidaNested
from .marca import MarcaNested
from ..models.enums import EstadoEnum
from .pagination import Pagination

# --- Nuevos esquemas para Conversiones de Compra ---

class ConversionesCompraBase(BaseModel):
    nombre_presentacion: str
    unidad_inventario_por_presentacion: Decimal

    model_config = ConfigDict(json_encoders={Decimal: str})

class ConversionesCompraCreate(ConversionesCompraBase):
    pass

class ConversionesCompra(ConversionesCompraBase):
    conversion_id: int
    producto_id: int

    model_config = ConfigDict(from_attributes=True, json_encoders={Decimal: str})

# --- Esquemas de Producto actualizados ---

class ProductoBase(BaseModel):
    codigo: str
    nombre: str
    precio_compra: Decimal
    precio_venta: Decimal
    stock_minimo: int
    categoria_id: int
    unidad_inventario_id: int  # Renombrado
    marca_id: int
    unidad_compra_predeterminada: Optional[str] = None # Nuevo

class ProductoCreate(ProductoBase):
    imagen_ruta: Optional[str] = None
    stock: Optional[Decimal] = Decimal('0.0') # Ahora es Decimal
    estado: Optional[EstadoEnum] = EstadoEnum.activo

class ProductoUpdate(ProductoBase):
    codigo: Optional[str] = None
    nombre: Optional[str] = None
    precio_compra: Optional[Decimal] = None
    precio_venta: Optional[Decimal] = None
    stock: Optional[Decimal] = None  # Ahora es Decimal
    stock_minimo: Optional[int] = None
    categoria_id: Optional[int] = None
    imagen_ruta: Optional[str] = None
    estado: Optional[EstadoEnum] = None
    unidad_inventario_id: Optional[int] = None # Renombrado
    marca_id: Optional[int] = None
    unidad_compra_predeterminada: Optional[str] = None # Nuevo

class Producto(ProductoBase):
    producto_id: int
    imagen_ruta: Optional[str] = None
    stock: Decimal # Ahora es Decimal
    estado: EstadoEnum
    creado_por: Optional[int] = None
    modificado_por: Optional[int] = None

    # Entidades relacionadas anidadas
    categoria: CategoriaNested
    creador: Optional[UsuarioAudit] = None
    modificador: Optional[UsuarioAudit] = None
    unidad_inventario: UnidadMedidaNested  # Renombrado
    marca: MarcaNested
    
    # Nueva relación anidada
    conversiones: List[ConversionesCompra] = []

    model_config = ConfigDict(from_attributes=True, json_encoders={Decimal: str})

class ProductoNested(BaseModel):
    producto_id: int
    codigo: str
    nombre: str
    precio_venta: Decimal
    imagen_ruta: Optional[str] = None
    stock: Decimal # Ahora es Decimal
    unidad_inventario: UnidadMedidaNested # Para mostrar la unidad base

    model_config = ConfigDict(from_attributes=True, json_encoders={Decimal: str})
    

class ProductoCompra(BaseModel):
    producto_id: int
    codigo: str
    nombre: str
    precio_compra: Decimal
    imagen_ruta: Optional[str] = None
    stock: Decimal # Ahora es Decimal

    model_config = ConfigDict(from_attributes=True, json_encoders={Decimal: str})

class ProductoPagination(Pagination[Producto]):
    """Esquema para la respuesta paginada de productos."""
    pass
