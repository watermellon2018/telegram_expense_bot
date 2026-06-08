"""${message}

Revision ID: ${up_revision}
Revises: ${down_revision | comma,n}
Create Date: ${create_date}

Миграции в этом проекте пишутся ВРУЧНУЮ через op.execute(...) с идемпотентным SQL
(CREATE TABLE IF NOT EXISTS, ADD COLUMN IF NOT EXISTS, DO $$ ... IF NOT EXISTS $$).
autogenerate не используется (в проекте нет ORM-моделей).
"""
from alembic import op
import sqlalchemy as sa
${imports if imports else ""}

# revision identifiers, used by Alembic.
revision = ${repr(up_revision)}
down_revision = ${repr(down_revision)}
branch_labels = ${repr(branch_labels)}
depends_on = ${repr(depends_on)}


def upgrade() -> None:
    ${upgrades if upgrades else "pass"}


def downgrade() -> None:
    ${downgrades if downgrades else "pass"}
