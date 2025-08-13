# backEnd/app/models/rol_menu.py
from sqlalchemy import Column, Integer, ForeignKey
from sqlalchemy.orm import relationship
from .base import Base

class RolMenu(Base):
    __tablename__ = 'rol_menus'

    rol_id = Column(Integer, ForeignKey('roles.rol_id'), primary_key=True)
    menu_id = Column(Integer, ForeignKey('menus.menu_id'), primary_key=True)

    # Relaciones con las tablas Rol y Menu
    rol = relationship("Rol", back_populates="rol_menus", overlaps="menus,roles")
    menu = relationship("Menu", back_populates="rol_menus", overlaps="roles,menus")

    def __repr__(self):
        return f"<RolMenu(rol_id={self.rol_id}, menu_id={self.menu_id})>"
