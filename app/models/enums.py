from enum import Enum

class GeneroEnum(str, Enum): # Usamos str, enum.Enum
    M = "M"
    F = "F"

     
class EstadoEnum(str, Enum): 
    activo = "activo"
    inactivo = "inactivo"
    bloqueado = "bloqueado" 
    
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

class TipoMovimientoEnum(str, Enum):
    merma = "merma"
    ajuste_positivo = "ajuste_positivo"
    ajuste_negativo = "ajuste_negativo"
    uso_interno = "uso_interno"