from enum import Enum

class GeneroEnum(str, Enum): # Usamos str, enum.Enum
    M = "M"
    F = "F"

     
class EstadoEnum(str, Enum): # Usamos str, enum.Enum para que SQLAlchemy mapee a VARCHAR
    activo = "activo"
    inactivo = "inactivo"
    bloqueado = "bloqueado" # Para usuarios
    
class EstadoCompraEnum(str, Enum):
     pendiente = "pendiente"
     completada = "completada"
     anulada = "anulada"

class EstadoVentaEnum(str, Enum):
     activa = "activa"
     anulada = "anulada"

class TipoMargenEnum(str, Enum):
    porcentaje = "porcentaje"
    fijo = "fijo"