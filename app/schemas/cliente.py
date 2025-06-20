# backEnd/app/schemas/cliente.py
from pydantic import BaseModel
from typing import Optional


class PersonaNested(BaseModel):
    persona_id: int
    nombre: str
    apellido_paterno: Optional[str] = None
    apellido_materno: Optional[str] = None
    ci: Optional[str] = None
    telefono: Optional[str] = None
    email: Optional[str] = None
    direccion: Optional[str] = None
    class Config:
        from_attributes = True

class ClienteBase(BaseModel):
    persona_id: int


class ClienteCreate(ClienteBase):
    pass

class ClienteNested(ClienteBase):
    cliente_id: int
    # Anidamos la información de la persona
    persona: PersonaNested

    class Config:
        from_attributes = True

class Cliente(ClienteNested):
    estado: str

    class Config:
        from_attributes = True