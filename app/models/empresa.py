# backEnd/app/models/empresa.py
from sqlalchemy import Column, Integer, String, Text, Enum # Importa Text para el campo direccion
from sqlalchemy.orm import relationship

from .base import Base # Importa la base declarativa
from .enums import EstadoEnum # Importa el Enum de estado

# Nota: Este modelo mapea la tabla empresas.

class Empresa(Base):
    __tablename__ = "empresas" # Mapea a la tabla 'empresas' en la base de datos

    empresa_id = Column(Integer, primary_key=True, index=True) # Clave primaria
    razon_social = Column(String(150), nullable=False) # Razón social no nula
    nombre_contacto = Column(String(100), nullable=True) # Nombre de contacto (puede ser nulo)
    identificacion = Column(String(50), unique=True, nullable=True) # Identificación única (puede ser nulo, aunque UNIQUE con NULL tiene matices en SQL)
    telefono = Column(String(20), nullable=True) # Teléfono (puede ser nulo)
    email = Column(String(100), unique=True, nullable=True) # Email (puede ser nulo)
    direccion = Column(Text, nullable=True) # Dirección usando tipo Text (puede ser nulo)

    # Campo de estado con Enum y default
    estado = Column(Enum(EstadoEnum), default=EstadoEnum.activo, nullable=False) # Usa el Enum y default

    # Definir la relación inversa a Proveedor (1:1)
    # back_populates debe coincidir con la relación 'empresa' en el modelo Proveedor
    proveedor = relationship("Proveedor", back_populates="empresa", uselist=False) # uselist=False para 1:1


    # El método __repr__ es útil para la depuración
    def __repr__(self):
        return f"<Empresa(empresa_id={self.empresa_id}, razon_social='{self.razon_social}', identificacion='{self.identificacion}', estado='{self.estado}')>"

