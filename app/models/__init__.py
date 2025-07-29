#aqui se el __init__.py para importar las clases y funciones necesarias
from .base import Base
from .usuario import Usuario
from .rol import Rol
from .categoria import Categoria # Importa el modelo Categoria
from .persona import Persona # Importa el modelo Persona
from .enums import EstadoEnum, GeneroEnum # Importa los enums
from .empresa import Empresa # Importa el modelo Empresa
from .proveedor import Proveedor # Importa el modelo Proveedor
from .producto import Producto # Importa el modelo Productos
from .compra import Compra # Importa el modelo Compra
from .detalle_compra import DetalleCompra # Importa el modelo DetalleCompra
from .venta import Venta
from .detalle_venta import DetalleVenta
from .metodo_pago import MetodoPago
from .marca import Marca
from .unidad_medida import UnidadMedida
from .persona_rol import PersonaRol # Importa la nueva tabla de asociación Persona-Rol
from .movimiento import MovimientoInventario # Importa el modelo MovimientoInventario    