# backEnd/app/schemas/menu.py
from pydantic import BaseModel, ConfigDict
from typing import Optional, List

# --- Esquema base para Menu ---
class MenuBase(BaseModel):
    nombre: str
    ruta: str
    descripcion: Optional[str] = None
    icono: Optional[str] = None

class MenuInDB(BaseModel):
    menu_id: int
    nombre: str
    ruta: str
    descripcion: Optional[str] = None
    icono: Optional[str] = None
    
    class Config:
        from_attributes = True  # Para SQLAlchemy ORM

class RolMenuUpdate(BaseModel):
    menu_ids: List[int] = []