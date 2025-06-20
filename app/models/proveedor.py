# backEnd/app/models/proveedor.py
from sqlalchemy import Column, Integer, String, ForeignKey, Enum, CheckConstraint # Importa CheckConstraint
from sqlalchemy.orm import relationship

from .base import Base # Importa la base declarativa
from .enums import EstadoEnum # Importa el Enum de estado
# Importa los modelos relacionados para definir las relaciones
from .persona import Persona
from .empresa import Empresa

# Nota: Este modelo mapea la tabla proveedores con la relación exclusiva a Persona o Empresa.

class Proveedor(Base):
    __tablename__ = "proveedores" # Mapea a la tabla 'proveedores' en la base de datos

    proveedor_id = Column(Integer, primary_key=True, index=True) # Clave primaria

    # Claves Foráneas a Persona y Empresa (ambas pueden ser NULL)
    persona_id = Column(Integer, ForeignKey('personas.persona_id', ondelete='RESTRICT'), nullable=True)
    empresa_id = Column(Integer, ForeignKey('empresas.empresa_id', ondelete='RESTRICT'), nullable=True)

    # Campo de estado con Enum y default
    estado = Column(Enum(EstadoEnum), default=EstadoEnum.activo, nullable=False) # Usa el Enum y default

    # Restricción CHECK de la base de datos replicada a nivel de SQLAlchemy (opcional pero útil para validación temprana)
    # Aunque la restricción de la DB es la garantía final.
    __table_args__ = (
        CheckConstraint(
            '(persona_id IS NOT NULL AND empresa_id IS NULL) OR (persona_id IS NULL AND empresa_id IS NOT NULL)',
            name='chk_un_solo_tipo'
        ),
    )

    # Definir relaciones ORM
    # Relación 1:1 con Persona (si aplica)
    # Usamos uselist=False para indicar una relación a un solo objeto
    # back_populates debe coincidir con la relación inversa en el modelo Persona
    persona = relationship("Persona", back_populates="proveedor", uselist=False)

    # Relación 1:1 con Empresa (if applies)
    # back_populates must match the inverse relationship in the Empresa model
    empresa = relationship("Empresa", back_populates="proveedor", uselist=False)
    
    compras = relationship("Compra", back_populates="proveedor") # Relación 1:N con Compra


    # El método __repr__ es útil para la depuración
    def __repr__(self):
        tipo = "Persona" if self.persona_id else ("Empresa" if self.empresa_id else "Desconocido")
        return f"<Proveedor(proveedor_id={self.proveedor_id}, tipo='{tipo}', persona_id={self.persona_id}, empresa_id={self.empresa_id}, estado='{self.estado}')>"

# Asegúrate de que en los modelos Persona y Empresa tienes la relación inversa definida:
# # backEnd/app/models/persona.py (Fragmento)
# class Persona(Base):
#     # ... columnas ...
#     # *** AÑADE esta relación si aún no la tienes ***
#     proveedor = relationship("Proveedor", back_populates="persona", uselist=False) # uselist=False para 1:1
#     # ... otras relaciones (ej. usuario) ...

# # backEnd/app/models/empresa.py (Fragmento)
# class Empresa(Base):
#     # ... columnas ...
#     # *** AÑADE esta relación si aún no la tienes ***
#     proveedor = relationship("Proveedor", back_populates="empresa", uselist=False) # uselist=False para 1:1
#     # ...
