# backEnd/app/schemas/metodo_pago.py
from pydantic import BaseModel

class MetodoPagoBase(BaseModel):
    nombre_metodo: str

class MetodoPagoCreate(MetodoPagoBase):
    pass

class MetodoPagoNested(MetodoPagoBase):
    """Esquema para un método de pago cuando se anida en otra respuesta (ej. Venta)."""
    metodo_pago_id: int

    class Config:
        from_attributes = True

# Si necesitas un esquema más completo para listar/obtener métodos de pago
class MetodoPago(MetodoPagoNested):
    estado: str # Por si quieres exponer el estado

    class Config:
        from_attributes = True