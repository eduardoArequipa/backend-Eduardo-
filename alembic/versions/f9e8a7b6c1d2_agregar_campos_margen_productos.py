"""Agregar campos de margen y precio automático a productos

Revision ID: f9e8a7b6c1d2
Revises: cd0a09fcf82e
Create Date: 2025-09-04 15:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f9e8a7b6c1d2'
down_revision: Union[str, None] = 'cd0a09fcf82e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Crear el enum para tipo de margen
    tipo_margen_enum = sa.Enum('porcentaje', 'fijo', name='tipomargen')
    tipo_margen_enum.create(op.get_bind())

    # Agregar nuevos campos a la tabla productos
    op.add_column('productos', sa.Column('tipo_margen', 
                                         tipo_margen_enum, 
                                         server_default='porcentaje', 
                                         nullable=False))
    
    op.add_column('productos', sa.Column('margen_valor', 
                                         sa.DECIMAL(precision=10, scale=2), 
                                         server_default='30.0', 
                                         nullable=False))
    
    op.add_column('productos', sa.Column('precio_manual_activo', 
                                         sa.Boolean(), 
                                         server_default=sa.text('false'), 
                                         nullable=False))

    # Agregar constraint para validar que margen_valor sea no negativo
    op.create_check_constraint(
        'chk_margen_valor_no_negativo',
        'productos',
        'margen_valor >= 0'
    )


def downgrade() -> None:
    """Downgrade schema."""
    # Eliminar constraint
    op.drop_constraint('chk_margen_valor_no_negativo', 'productos', type_='check')
    
    # Eliminar columnas
    op.drop_column('productos', 'precio_manual_activo')
    op.drop_column('productos', 'margen_valor')
    op.drop_column('productos', 'tipo_margen')
    
    # Eliminar el enum
    tipo_margen_enum = sa.Enum('porcentaje', 'fijo', name='tipomargen')
    tipo_margen_enum.drop(op.get_bind())