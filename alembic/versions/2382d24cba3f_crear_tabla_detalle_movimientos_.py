"""Crear tabla detalle_movimientos_inventario

Revision ID: 2382d24cba3f
Revises: 
Create Date: 2025-10-30 01:44:09.605067

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '2382d24cba3f'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('detalle_movimientos_inventario',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('movimiento_id', sa.Integer(), nullable=False),
        sa.Column('conversion_id', sa.Integer(), nullable=True),
        sa.Column('cantidad', sa.Numeric(precision=10, scale=3), nullable=False),
        sa.ForeignKeyConstraint(['conversion_id'], ['conversiones.id'], ),
        sa.ForeignKeyConstraint(['movimiento_id'], ['movimientos_inventario.movimiento_id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )


def downgrade() -> None:
    op.drop_table('detalle_movimientos_inventario')
