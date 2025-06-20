# backEnd/app/schemas/empresa.py
from typing import Optional
from pydantic import BaseModel, ConfigDict

from ..models.enums import EstadoEnum


class EmpresaBase(BaseModel):
    razon_social: str # Razón social es requerida
    # identificacion: Optional[str] = None # La identificación puede ser opcional si no siempre se proporciona


class EmpresaCreate(EmpresaBase):
    identificacion: Optional[str] = None 
    nombre_contacto: Optional[str] = None 
    telefono: Optional[str] = None 
    email: Optional[str] = None 
    direccion: Optional[str] = None 



class EmpresaUpdate(EmpresaBase): 
    razon_social: Optional[str] = None 
    identificacion: Optional[str] = None 
    nombre_contacto: Optional[str] = None
    telefono: Optional[str] = None
    email: Optional[str] = None
    direccion: Optional[str] = None
    estado: Optional[EstadoEnum] = None 


class Empresa(EmpresaBase):
    empresa_id: int 
    identificacion: Optional[str] = None 
    nombre_contacto: Optional[str] = None
    telefono: Optional[str] = None
    email: Optional[str] = None
    direccion: Optional[str] = None
    estado: EstadoEnum 
    
    model_config = ConfigDict(from_attributes=True)



# Esquema Anidado: Representación más simple de Empresa, útil para anidar en otros esquemas (ej. Proveedor)
class EmpresaNested(EmpresaBase):
    empresa_id: int
    identificacion: Optional[str] = None 
    nombre_contacto: Optional[str] = None 
    telefono: Optional[str] = None 
    email: Optional[str] = None 
    direccion: Optional[str] = None 
    estado: EstadoEnum 