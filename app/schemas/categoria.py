# backEnd/app/schemas/categoria.py
from typing import Optional, List 
from pydantic import BaseModel, ConfigDict 
from ..models.enums import EstadoEnum

class CategoriaBase(BaseModel):
    nombre_categoria: str 

class CategoriaCreate(CategoriaBase):

    pass # No necesita campos adicionales si solo se envía nombre_categoria


class CategoriaUpdate(CategoriaBase):
    nombre_categoria: Optional[str] = None
    estado: Optional[EstadoEnum] = None 
class Categoria(CategoriaBase):
    categoria_id: int 
    estado: EstadoEnum 


    model_config = ConfigDict(from_attributes=True)



class CategoriaNested(BaseModel):
    categoria_id: int
    nombre_categoria: str

    model_config = ConfigDict(from_attributes=True)
