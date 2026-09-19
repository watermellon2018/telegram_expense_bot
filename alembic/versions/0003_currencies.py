"""Currency snapshots, account preferences and shared daily FX cache.

Legacy monetary rows deliberately remain untyped. All DDL is idempotent.
No exchange rates are requested and no historical amounts are changed.
"""

from alembic import op

revision = "0003_currencies"
down_revision = "0002_project_categories_isolated"
branch_labels = None
depends_on = None

SCHEMA_SQL = """
ALTER TABLE users ADD COLUMN IF NOT EXISTS reporting_currency TEXT NOT NULL DEFAULT 'RUB';
ALTER TABLE projects ADD COLUMN IF NOT EXISTS reporting_currency TEXT NOT NULL DEFAULT 'RUB';
CREATE TABLE IF NOT EXISTS currency_preferences (
    user_id TEXT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    project_id INTEGER REFERENCES projects(project_id) ON DELETE CASCADE,
    currency TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS currency_preferences_context_idx
    ON currency_preferences(user_id,COALESCE(project_id,0));
CREATE TABLE IF NOT EXISTS currency_fallback_rates (
    user_id TEXT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    project_id INTEGER REFERENCES projects(project_id) ON DELETE CASCADE,
    source_currency TEXT NOT NULL,
    target_currency TEXT NOT NULL,
    rate NUMERIC NOT NULL CHECK (rate > 0 AND rate < 'Infinity'::numeric),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX IF NOT EXISTS currency_fallback_context_pair_idx
    ON currency_fallback_rates(COALESCE(project_id,0),
        (CASE WHEN project_id IS NULL THEN user_id ELSE '' END),source_currency,target_currency);
CREATE TABLE IF NOT EXISTS currency_daily_rates (
    requested_date DATE PRIMARY KEY,
    effective_date DATE NOT NULL CHECK (effective_date <= requested_date),
    rates JSONB NOT NULL CHECK (jsonb_typeof(rates)='object'),
    fetched_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
ALTER TABLE recurring_rules ADD COLUMN IF NOT EXISTS currency TEXT;
ALTER TABLE recurring_incomes ADD COLUMN IF NOT EXISTS currency TEXT;
ALTER TABLE budgets ADD COLUMN IF NOT EXISTS currency TEXT;
ALTER TABLE project_member_settings ADD COLUMN IF NOT EXISTS threshold_currency TEXT;
ALTER TABLE cashback_monthly_snapshots ADD COLUMN IF NOT EXISTS currency TEXT;
"""

SUPPORTED = "'RUB','USD','EUR','JPY','CNY','THB','AED','TRY','GBP','KZT','GEL','KRW'"


def _constraint(table: str, name: str, expression: str) -> None:
    # All identifiers/expressions are migration-owned constants, never user input.
    op.execute(f"""DO $$ BEGIN
        IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='{name}'
                       AND conrelid='public.{table}'::regclass) THEN
            ALTER TABLE public.{table} ADD CONSTRAINT {name} CHECK ({expression});
        END IF;
    END $$;""")


def upgrade() -> None:
    op.execute(SCHEMA_SQL)
    # A removed project must never turn an automatic project payment into a
    # personal payment (potentially with a different reporting currency).
    for table in ("recurring_rules", "recurring_incomes"):
        op.execute(f"""DO $$ DECLARE fk RECORD; BEGIN
            FOR fk IN SELECT conname FROM pg_constraint
                WHERE conrelid='public.{table}'::regclass
                  AND confrelid='public.projects'::regclass AND contype='f'
                  AND confdeltype <> 'c'
            LOOP
                EXECUTE format('ALTER TABLE public.{table} DROP CONSTRAINT %I', fk.conname);
            END LOOP;
            IF NOT EXISTS (SELECT 1 FROM pg_constraint
                WHERE conrelid='public.{table}'::regclass
                  AND confrelid='public.projects'::regclass AND contype='f') THEN
                ALTER TABLE public.{table} ADD CONSTRAINT {table}_project_id_fkey
                    FOREIGN KEY (project_id) REFERENCES public.projects(project_id) ON DELETE CASCADE;
            END IF;
        END $$;""")
    for table in ("expenses", "incomes"):
        op.execute(f"""ALTER TABLE public.{table}
            ADD COLUMN IF NOT EXISTS currency TEXT,
            ADD COLUMN IF NOT EXISTS reporting_amount NUMERIC,
            ADD COLUMN IF NOT EXISTS reporting_currency TEXT,
            ADD COLUMN IF NOT EXISTS fx_rate NUMERIC,
            ADD COLUMN IF NOT EXISTS fx_date DATE,
            ADD COLUMN IF NOT EXISTS fx_source TEXT;""")
        fields = "currency,reporting_amount,reporting_currency,fx_rate,fx_date,fx_source"
        _constraint(table, f"{table}_currency_snapshot_complete",
                    f"num_nonnulls({fields})=0 OR (num_nonnulls({fields})=6 "
                    "AND amount IS NOT NULL AND amount > 0 AND amount < 'Infinity'::numeric "
                    "AND reporting_amount >= 0 AND reporting_amount < 'Infinity'::numeric "
                    "AND fx_rate > 0 AND fx_rate < 'Infinity'::numeric "
                    "AND fx_source IN ('identity','cbr','manual'))")
        _constraint(table, f"{table}_currency_code", f"currency IN ({SUPPORTED})")
        _constraint(table, f"{table}_reporting_currency_code", f"reporting_currency IN ({SUPPORTED})")
    for table, columns in {
        "users": ("reporting_currency",), "projects": ("reporting_currency",),
        "currency_preferences": ("currency",), "currency_fallback_rates": ("source_currency", "target_currency"),
        "recurring_rules": ("currency",), "recurring_incomes": ("currency",),
        "budgets": ("currency",), "project_member_settings": ("threshold_currency",),
        "cashback_monthly_snapshots": ("currency",),
    }.items():
        for column in columns:
            _constraint(table, f"{table}_{column}_code", f"{column} IN ({SUPPORTED})")
    op.execute("""CREATE OR REPLACE VIEW reporting_expenses AS
        SELECT id,user_id,project_id,date,time,reporting_amount AS amount,category,description,
               month,category_id,source_type,recurring_rule_id,created_by_system,created_at,deleted_at,
               amount AS original_amount,currency,reporting_amount,reporting_currency,fx_rate,fx_date,fx_source
        FROM expenses WHERE currency IS NOT NULL AND deleted_at IS NULL;
        CREATE OR REPLACE VIEW reporting_incomes AS
        SELECT id,user_id,reporting_amount AS amount,income_category_id,project_id,description,
               month,income_date,created_at,recurring_income_id,created_by_system,
               amount AS original_amount,currency,reporting_amount,reporting_currency,fx_rate,fx_date,fx_source
        FROM incomes WHERE currency IS NOT NULL;""")


def downgrade() -> None:
    raise RuntimeError("Currency snapshots cannot be removed without losing monetary meaning. Restore a backup instead.")
