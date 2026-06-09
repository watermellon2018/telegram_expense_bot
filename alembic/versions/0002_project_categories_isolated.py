"""project category templates: projects.categories_isolated

Revision ID: 0002_project_categories_isolated
Revises: 0001_baseline
Create Date: 2026-06-09

Добавляет флаг изоляции категорий проекта (фича «шаблоны проектов»).

Когда проект создаётся по тематическому шаблону (Отпуск/Ремонт/...), ему
копируется набор категорий шаблона и выставляется categories_isolated = TRUE.
Для такого проекта в списках/резолве категорий НЕ подмешиваются глобальные
категории владельца (project_id IS NULL) — видны только категории самого проекта.

Существующие проекты и «обычные» новые проекты остаются с categories_isolated =
FALSE и ведут себя как раньше (глобальные категории видны).

Идемпотентность: ADD COLUMN IF NOT EXISTS — безопасно и на пустой, и на уже
обновлённой БД. downgrade поддержан (аддитивное изменение): DROP COLUMN
IF EXISTS возвращает схему к baseline (изолированные проекты после отката снова
начнут видеть глобальные категории — деградация поведения, но не потеря данных).

Блокировка: ADD COLUMN ... DEFAULT <const> NOT NULL в PostgreSQL >= 11 — это
метаданная операция (таблица не переписывается), берёт короткий ACCESS EXCLUSIVE
lock; таблица projects небольшая, риск простоя пренебрежимо мал.
"""
from alembic import op

# revision identifiers, used by Alembic.
revision = "0002_project_categories_isolated"
down_revision = "0001_baseline"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE public.projects
            ADD COLUMN IF NOT EXISTS categories_isolated BOOLEAN NOT NULL DEFAULT FALSE;
        """
    )


def downgrade() -> None:
    op.execute(
        """
        ALTER TABLE public.projects
            DROP COLUMN IF EXISTS categories_isolated;
        """
    )
