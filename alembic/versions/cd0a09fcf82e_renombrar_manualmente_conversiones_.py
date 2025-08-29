"""Renombrar manualmente conversiones_compra a conversiones

Revision ID: cd0a09fcf82e
Revises: 
Create Date: 2025-08-24 23:09:36.764748

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'cd0a09fcf82e'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Renombrar la tabla
    op.rename_table('conversiones_compra', 'conversiones')

    # Renombrar columnas
    op.alter_column('conversiones', 'conversion_id', new_column_name='id')
    op.alter_column('conversiones', 'unidad_inventario_por_presentacion', new_column_name='unidades_por_presentacion')

    # Añadir nuevas columnas
    op.add_column('conversiones', sa.Column('es_para_compra', sa.Boolean(), server_default=sa.text('true'), nullable=False))
    op.add_column('conversiones', sa.Column('es_para_venta', sa.Boolean(), server_default=sa.text('false'), nullable=False))
    op.add_column('conversiones', sa.Column('es_activo', sa.Boolean(), server_default=sa.text('true'), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    # Revertir el renombrado de la tabla
    op.rename_table('conversiones', 'conversiones_compra')

    # Revertir el renombrado de columnas
    op.alter_column('conversiones_compra', 'id', new_column_name='conversion_id')
    op.alter_column('conversiones_compra', 'unidades_por_presentacion', new_column_name='unidad_inventario_por_presentacion')

    # Eliminar las columnas añadidas
    op.drop_column('conversiones_compra', 'es_para_compra')
    op.drop_column('conversiones_compra', 'es_para_venta')
    op.drop_column('conversiones_compra', 'es_activo')