# backEnd/app/models/menu.py
from sqlalchemy import Column, Integer, String, Text, ForeignKey
from sqlalchemy.orm import relationship
from .base import Base

class Menu(Base):
    __tablename__ = 'menus'

    menu_id = Column(Integer, primary_key=True, index=True)
    nombre = Column(String(100), nullable=False, unique=True)
    ruta = Column(String(255), nullable=False, unique=True)
    descripcion = Column(Text)
    icono = Column(String(50))
    padre_id = Column(Integer, ForeignKey('menus.menu_id'))

    # Relación a sí mismo para menús padre/hijo (útil para el futuro)
    parent = relationship("Menu", remote_side=[menu_id])
    
    # Relación con la tabla pivote rol_menus
    rol_menus = relationship("RolMenu", back_populates="menu", cascade="all, delete-orphan")

    # Relación muchos a muchos con Roles
    roles = relationship(
        "Rol",
        secondary="rol_menus",
        back_populates="menus",
        overlaps="rol_menus" # Silencia la advertencia de SQLAlchemy
    )

    def __repr__(self):
        return f"<Menu(id={self.menu_id}, nombre='{self.nombre}')>"
