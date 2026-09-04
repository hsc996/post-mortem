"""Rename mitigation_state's unique constraint to match the naming convention

Revision ID: b620b2c86e1b
Revises: bce7ac2167ea
Create Date: 2026-09-04 15:40:39.660265

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b620b2c86e1b'
down_revision: Union[str, Sequence[str], None] = 'bce7ac2167ea'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _constraint_exists(name: str) -> bool:
    bind = op.get_bind()
    return bool(
        bind.execute(
            sa.text("SELECT 1 FROM pg_constraint WHERE conname = :name"), {"name": name}
        ).scalar()
    )


def upgrade() -> None:
    """Renames the old Postgres-default constraint name to the naming-convention
    name. A database built from scratch after Base.metadata gained a naming
    convention already creates this constraint under the new name (Alembic's
    op.create_table picks up the convention from target_metadata), so this is a
    no-op there and only applies to databases migrated forward from before that
    change."""
    if _constraint_exists('mitigation_state_incident_id_key'):
        op.drop_constraint('mitigation_state_incident_id_key', 'mitigation_state', type_='unique')
        op.create_unique_constraint('uq_mitigation_state_incident_id', 'mitigation_state', ['incident_id'])


def downgrade() -> None:
    """Reverses the rename, but only if this migration actually performed it."""
    if _constraint_exists('uq_mitigation_state_incident_id') and not _constraint_exists(
        'mitigation_state_incident_id_key'
    ):
        op.drop_constraint('uq_mitigation_state_incident_id', 'mitigation_state', type_='unique')
        op.create_unique_constraint('mitigation_state_incident_id_key', 'mitigation_state', ['incident_id'])
