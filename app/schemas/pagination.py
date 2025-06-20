# backend/schemas/pagination.py
from typing import Generic, List, TypeVar
from pydantic import BaseModel

T = TypeVar('T')

class Pagination(BaseModel, Generic[T]):
    items: List[T] 
    total: int   

    class Config:

        from_attributes = True