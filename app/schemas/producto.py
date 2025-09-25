from typing import Optional, List
from pydantic import BaseModel, ConfigDict, Field
from decimal import Decimal
from .categoria import CategoriaNested
from .usuario import UsuarioAudit
from .unidad_medida import UnidadMedidaNested
from .marca import MarcaNested
from ..models.enums import EstadoEnum, TipoMargenEnum
from .pagination import Pagination

# --- Nuevos esquemas para Conversiones de Compra ---

class ConversionBase(BaseModel):
    nombre_presentacion: str
    unidades_por_presentacion: Decimal
    es_para_compra: bool
    es_para_venta: bool
    descripcion_detallada: Optional[str] = None

    model_config = ConfigDict(json_encoders={Decimal: str})

class ConversionCreate(ConversionBase):
    pass

class Conversion(ConversionBase):
    id: int
    producto_id: int
    es_activo: Optional[bool] = None # Add es_activo as it's in the model

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
    tipo_margen: Optional[TipoMargenEnum] = TipoMargenEnum.porcentaje
    margen_valor: Optional[Decimal] = Decimal('30.0')
    precio_manual_activo: Optional[bool] = False

class ProductoCreate(ProductoBase):
    imagen_ruta: Optional[str] = None
    stock: Optional[Decimal] = Decimal('0.0') # Stock decimal para fracciones
    estado: Optional[EstadoEnum] = EstadoEnum.activo

class ProductoUpdate(ProductoBase):
    codigo: Optional[str] = None
    nombre: Optional[str] = None
    precio_compra: Optional[Decimal] = None
    precio_venta: Optional[Decimal] = None
    stock: Optional[Decimal] = None  # Stock decimal para fracciones
    stock_minimo: Optional[int] = None
    categoria_id: Optional[int] = None
    imagen_ruta: Optional[str] = None
    estado: Optional[EstadoEnum] = None
    unidad_inventario_id: Optional[int] = None # Renombrado
    marca_id: Optional[int] = None
    unidad_compra_predeterminada: Optional[str] = None # Nuevo
    tipo_margen: Optional[TipoMargenEnum] = None
    margen_valor: Optional[Decimal] = None
    precio_manual_activo: Optional[bool] = None

class DesglosePresentacion(BaseModel):
    """Una presentación del desglose de stock"""
    nombre: str
    cantidad: Decimal  # Cambiar a Decimal para soportar fracciones
    abreviatura: str

    model_config = ConfigDict(json_encoders={Decimal: str})

class StockConvertido(BaseModel):
    """Información del stock convertido a unidad de venta preferida"""
    cantidad: Decimal
    unidad_nombre: str
    unidad_abreviatura: str
    es_aproximado: bool = False  # Si la conversión no es exacta
    
    model_config = ConfigDict(json_encoders={Decimal: str})

class Producto(ProductoBase):
    producto_id: int
    imagen_ruta: Optional[str] = None
    stock: Decimal # Stock decimal para fracciones
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
    conversiones: List[Conversion] = []
    
    # Nuevo campo calculado para stock en unidad de venta preferida
    stock_convertido: Optional[StockConvertido] = None
    # Nuevo campo para el desglose detallado
    stock_desglosado: Optional[List[DesglosePresentacion]] = None

    model_config = ConfigDict(from_attributes=True, json_encoders={Decimal: str})

class ProductoNested(BaseModel):
    producto_id: int
    codigo: str
    nombre: str
    precio_venta: Decimal
    imagen_ruta: Optional[str] = None
    stock: Decimal # Stock decimal para fracciones
    unidad_inventario: UnidadMedidaNested # Para mostrar la unidad base

    model_config = ConfigDict(from_attributes=True, json_encoders={Decimal: str})
    

class ProductoCompra(BaseModel):
    producto_id: int
    codigo: str
    nombre: str
    precio_compra: Decimal
    imagen_ruta: Optional[str] = None
    stock: Decimal # Stock decimal para fracciones

    model_config = ConfigDict(from_attributes=True, json_encoders={Decimal: str})

# Esquema para calcular precios sugeridos
class PrecioSugeridoRequest(BaseModel):
    precio_compra: Decimal
    tipo_margen: TipoMargenEnum
    margen_valor: Decimal

    model_config = ConfigDict(json_encoders={Decimal: str})

class PrecioSugeridoResponse(BaseModel):
    precio_compra: Decimal
    precio_venta_sugerido: Decimal
    tipo_margen: TipoMargenEnum
    margen_valor: Decimal
    margen_aplicado: Decimal  # Monto real del margen aplicado

    model_config = ConfigDict(json_encoders={Decimal: str})

class ProductoPagination(Pagination[Producto]):
    """Esquema para la respuesta paginada de productos."""
    pass
