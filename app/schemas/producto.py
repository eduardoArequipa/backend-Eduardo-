from typing import Optional, List
from pydantic import BaseModel, ConfigDict, Field
from decimal import Decimal 
from .categoria import CategoriaNested
from .usuario import UsuarioAudit
from .unidad_medida import UnidadMedidaNested 
from .marca import MarcaNested             
from ..models.enums import EstadoEnum

class ProductoBase(BaseModel):
    codigo: str
    nombre: str
    precio_compra: Decimal  
    precio_venta: Decimal  
    stock_minimo: int 
    categoria_id: int
    unidad_medida_id: int  
    marca_id: int         

class ProductoCreate(ProductoBase):
    imagen_ruta: Optional[str] = None
    stock: Optional[int] = int('0') 
    estado: Optional[EstadoEnum] = EstadoEnum.activo 
    metros_por_rollo: Optional[Decimal] = Field(None, description="Longitud en metros por rollo (solo para unidades de medida 'metro')")

class ProductoUpdate(ProductoBase):
    codigo: Optional[str] = None
    nombre: Optional[str] = None
    precio_compra: Optional[Decimal] = None
    precio_venta: Optional[Decimal] = None
    stock: Optional[int] = None  # Soporta fracciones
    stock_minimo: Optional[int] = None
    categoria_id: Optional[int] = None
    imagen_ruta: Optional[str] = None
    estado: Optional[EstadoEnum] = None
    unidad_medida_id: Optional[int] = None
    marca_id: Optional[int] = None
    metros_por_rollo: Optional[Decimal] = Field(None, description="Longitud en metros por rollo (solo para unidades de medida 'metro')")

class Producto(ProductoBase):
    producto_id: int
    imagen_ruta: Optional[str] = None
    stock: int 
    estado: EstadoEnum
    creado_por: Optional[int] = None
    modificado_por: Optional[int] = None

    # Entidades relacionadas anidadas
    categoria: CategoriaNested
    creador: Optional[UsuarioAudit] = None
    modificador: Optional[UsuarioAudit] = None
    unidad_medida: UnidadMedidaNested  
    marca: MarcaNested                
    metros_por_rollo: Optional[Decimal] = Field(None, description="Longitud en metros por rollo (solo para unidades de medida 'metro')")

    model_config = ConfigDict(from_attributes=True)

class ProductoNested(BaseModel):
    producto_id: int
    codigo: str
    nombre: str
    precio_venta: Decimal
    imagen_ruta: Optional[str] = None
    stock: int 
    metros_por_rollo: Optional[Decimal] = Field(None, description="Longitud en metros por rollo (solo para unidades de medida 'metro')")

    model_config = ConfigDict(from_attributes=True)
    

class ProductoCompra(BaseModel):
    producto_id: int
    codigo: str
    nombre: str
    precio_compra: Decimal
    imagen_ruta: Optional[str] = None
    stock: int 

    model_config = ConfigDict(from_attributes=True)