# backEnd/app/schemas/proveedor.py
from typing import Optional, Union
from pydantic import BaseModel, ConfigDict, field_validator, model_validator # Importa field_validator y model_validator
from pydantic import ValidationError

from ..models.enums import EstadoEnum

from .persona import PersonaNested, PersonaCreate, PersonaUpdate 
from .empresa import EmpresaNested, EmpresaCreate, EmpresaUpdate 



class ProveedorBase(BaseModel):
    estado: Optional[EstadoEnum] = EstadoEnum.activo 



class ProveedorCreate(ProveedorBase):
    persona_id: Optional[int] = None
    empresa_id: Optional[int] = None
    persona_data: Optional[PersonaCreate] = None 
    empresa_data: Optional[EmpresaCreate] = None



    @model_validator(mode='after') # Usa model_validator para validar el modelo completo
    def check_exclusive_association_or_creation(self) -> 'ProveedorCreate':
        provided_options = sum([
            self.persona_id is not None,
            self.empresa_id is not None,
            self.persona_data is not None,
            self.empresa_data is not None,
        ])
        if provided_options != 1:
            raise ValueError('Debe proporcionar exactamente una de las siguientes opciones: persona_id, empresa_id, persona_data, o empresa_data.')
        return self


class ProveedorUpdate(BaseModel): 
    estado: Optional[EstadoEnum] = None 


    persona_data: Optional[PersonaUpdate] = None 
    empresa_data: Optional[EmpresaUpdate] = None 

 


class Proveedor(ProveedorBase):
    proveedor_id: int

    persona: Optional[PersonaNested] = None
    empresa: Optional[EmpresaNested] = None

    model_config = ConfigDict(from_attributes=True)


class ProveedorNested(BaseModel):
    proveedor_id: int
    persona: Optional[PersonaNested] = None 
    empresa: Optional[EmpresaNested] = None 
    model_config = ConfigDict(from_attributes=True)

