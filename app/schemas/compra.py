# backEnd/app/schemas/compra.py
from typing import List, Optional
from datetime import datetime
from decimal import Decimal 
from pydantic import BaseModel, ConfigDict 

from ..models.enums import EstadoCompraEnum 
from .proveedor import ProveedorNested
from .usuario import UsuarioAudit 
from .producto import ProductoNested, ProductoBase
from .pagination import Pagination # Importar la clase Pagination

class DetalleCompraBase(BaseModel):
    producto_id: int 
    cantidad: int 
    precio_unitario: Decimal    
    model_config = ConfigDict(json_encoders={Decimal: str})

class DetalleCompraCreate(DetalleCompraBase):
    pass



class DetalleCompraUpdate(DetalleCompraBase):
     # En una actualización, podrías enviar el detalle_id si necesitas identificarlo
     detalle_id: int
     producto_id: Optional[int] = None  
     cantidad: Optional[int] = None
     precio_unitario: Optional[Decimal] = None

     # Configuración para manejar Decimal correctamente
     model_config = ConfigDict(json_encoders={Decimal: str})

class DetalleCompra(DetalleCompraBase):
    detalle_id: int 
    compra_id: int 
    producto: ProductoNested 
    model_config = ConfigDict(from_attributes=True, json_encoders={Decimal: str})


# Opcional: Esquema anidado de DetalleCompra, si necesitas una representación más simple
class DetalleCompraNested(DetalleCompraBase):
     detalle_id: int
     model_config = ConfigDict(from_attributes=True, json_encoders={Decimal: str})



# Esquema Base para Compra
class CompraBase(BaseModel):
    proveedor_id: int 

    estado: Optional[EstadoCompraEnum] = EstadoCompraEnum.pendiente 
    model_config = ConfigDict(json_encoders={Decimal: str})


class CompraCreate(CompraBase):
    detalles: List[DetalleCompraCreate]
    fecha_compra: Optional[datetime] = None
    model_config = ConfigDict(json_encoders={Decimal: str})



# backEnd/app/schemas/compra.py
from typing import List, Optional
from datetime import datetime
from decimal import Decimal 
from pydantic import BaseModel, ConfigDict 

from ..models.enums import EstadoCompraEnum 
from .proveedor import ProveedorNested
from .usuario import UsuarioAudit 
from .producto import ProductoNested
from .pagination import Pagination # Importar la clase Pagination

class DetalleCompraBase(BaseModel):
    producto_id: int 
    cantidad: int 
    precio_unitario: Decimal
    presentacion_compra: Optional[str] = None # Nuevo campo

    model_config = ConfigDict(json_encoders={Decimal: str})

class DetalleCompraCreate(DetalleCompraBase):
    pass



class DetalleCompraUpdate(DetalleCompraBase):
     # En una actualización, podrías enviar el detalle_id si necesitas identificarlo
     detalle_id: int
     producto_id: Optional[int] = None  
     cantidad: Optional[int] = None
     precio_unitario: Optional[Decimal] = None
     presentacion_compra: Optional[str] = None # Nuevo campo

     # Configuración para manejar Decimal correctamente
     model_config = ConfigDict(json_encoders={Decimal: str})

class DetalleCompra(DetalleCompraBase):
    detalle_id: int 
    compra_id: int 
    producto: ProductoNested 
    model_config = ConfigDict(from_attributes=True, json_encoders={Decimal: str})


# Opcional: Esquema anidado de DetalleCompra, si necesitas una representación más simple
class DetalleCompraNested(DetalleCompraBase):
     detalle_id: int
     model_config = ConfigDict(from_attributes=True, json_encoders={Decimal: str})



# Esquema Base para Compra
class CompraBase(BaseModel):
    proveedor_id: int 

    estado: Optional[EstadoCompraEnum] = EstadoCompraEnum.pendiente 
    model_config = ConfigDict(json_encoders={Decimal: str})


class CompraCreate(CompraBase):
    detalles: List[DetalleCompraCreate]
    fecha_compra: Optional[datetime] = None
    model_config = ConfigDict(json_encoders={Decimal: str})



# Permite actualizar estado y opcionalmente los detalles (esto último es más complejo y podría requerir lógica de "upsert")
class CompraUpdate(BaseModel):
    proveedor_id: Optional[int] = None 
    fecha_compra: Optional[datetime] = None 
    estado: Optional[EstadoCompraEnum] = None 
    detalles: Optional[List[DetalleCompraCreate]] = None # <--- CORREGIDO: Ahora espera DetalleCompraCreate

    model_config = ConfigDict(json_encoders={Decimal: str})


class Compra(CompraBase):
    compra_id: int 
    fecha_compra: datetime
    total: Decimal
    proveedor: ProveedorNested
    creador: Optional[UsuarioAudit] = None
    modificador: Optional[UsuarioAudit] = None 
    detalles: List[DetalleCompra] 
    model_config = ConfigDict(from_attributes=True, json_encoders={Decimal: str})


class CompraNested(CompraBase):
    compra_id: int
    fecha_compra: datetime
    total: Decimal


    model_config = ConfigDict(from_attributes=True, json_encoders={Decimal: str})

class CompraPagination(Pagination[Compra]):
    """Esquema para la respuesta paginada de compras."""
    pass



class Compra(CompraBase):
    compra_id: int 
    fecha_compra: datetime
    total: Decimal
    proveedor: ProveedorNested
    creador: Optional[UsuarioAudit] = None
    modificador: Optional[UsuarioAudit] = None 
    detalles: List[DetalleCompra] 
    model_config = ConfigDict(from_attributes=True, json_encoders={Decimal: str})


class CompraNested(CompraBase):
    compra_id: int
    fecha_compra: datetime
    total: Decimal


    model_config = ConfigDict(from_attributes=True, json_encoders={Decimal: str})

class CompraPagination(Pagination[Compra]):
    """Esquema para la respuesta paginada de compras."""
    pass