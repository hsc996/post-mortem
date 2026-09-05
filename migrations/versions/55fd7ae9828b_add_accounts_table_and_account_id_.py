"""add accounts table and account_id tenant scoping

Revision ID: 55fd7ae9828b
Revises: 6f42612b6673
Create Date: 2026-09-05 15:32:53.372501

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '55fd7ae9828b'
down_revision: str | Sequence[str] | None = '6f42612b6673'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Fixed, deterministic (not uuid4()) so it's identifiable/greppable in any
# environment this migration runs against.
LEGACY_ACCOUNT_ID = '00000000-0000-0000-0000-000000000000'
TENANT_TABLES = ('users', 'incidents', 'mitigation_state', 'audit_logs', 'invites')


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('accounts',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('name', sa.String(length=255), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_accounts'))
    )

    # Seed a legacy account for any pre-existing (accountless) rows before
    # tenancy existed, so the backfill below has something to point at.
    op.execute(
        "INSERT INTO accounts (id, name, created_at, updated_at) "
        f"VALUES ('{LEGACY_ACCOUNT_ID}', 'Legacy Account (pre-tenancy data)', now(), now())"
    )

    # Add account_id nullable first, backfill every existing row to the
    # legacy account, THEN enforce NOT NULL — protects real existing data
    # (local and Render both already have live demo users/incidents).
    for table in TENANT_TABLES:
        op.add_column(table, sa.Column('account_id', sa.UUID(), nullable=True))
    for table in TENANT_TABLES:
        op.execute(f"UPDATE {table} SET account_id = '{LEGACY_ACCOUNT_ID}'")
    for table in TENANT_TABLES:
        op.alter_column(table, 'account_id', nullable=False)

    for table in TENANT_TABLES:
        op.create_foreign_key(
            op.f(f'fk_{table}_account_id_accounts'), table, 'accounts', ['account_id'], ['id']
        )
        op.create_index(op.f(f'ix_{table}_account_id'), table, ['account_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    for table in TENANT_TABLES:
        op.drop_index(op.f(f'ix_{table}_account_id'), table_name=table)
        op.drop_constraint(op.f(f'fk_{table}_account_id_accounts'), table, type_='foreignkey')
        op.drop_column(table, 'account_id')
    op.drop_table('accounts')
