---
name: database-change
description: >-
  Изменение схемы PostgreSQL в этом expense-боте через Alembic-миграции. Пишет
  новую ревизию вручную (op.execute с идемпотентным SQL — autogenerate не
  используется, ORM нет), проверяет совместимость с данными, продумывает
  downgrade, server defaults, nullable, индексы/ограничения, блокировки больших
  таблиц; не редактирует уже применённые ревизии. Используй для задач изменения БД
  ("/database-change добавить таблицу настроек уведомлений проекта").
---

# Database Change

Изменение схемы PostgreSQL через **Alembic** (`alembic.ini`, `alembic/`). Проект на сыром SQL + asyncpg, **ORM/SQLAlchemy-моделей нет**, поэтому `--autogenerate` **не используется** — DDL в ревизии пишется **вручную** через `op.execute(...)` идемпотентным SQL. Рантайм бота работает на asyncpg; Alembic использует sync-драйвер psycopg, URL берёт из `DB_*` (см. `alembic/env.py`).

> **Docker не запускать.** На машине пользователя Docker Desktop не работает — не стартуй демон. Локальный Postgres на :5432 — это ЖИВОЙ dev `botdb`, к нему без явного разрешения не подключаться. Прогон миграций локально — в conda-окружении `telegram_bot` (Python 3.9) против отдельной тестовой БД, если она доступна; иначе пометь прогон как невыполнимый и опиши ручную проверку.

## Процедура

1. **Изучи текущую схему.** Прочитай baseline `alembic/versions/0001_baseline.py` (консолидирует всю схему) + последние ревизии в `alembic/versions/` + SQL-запросы в `utils/*`. Это источник правды по таблицам/колонкам/типам/ограничениям. Старые `migration/<feature>/*.sql` — архив (см. `migration/README.md`), новые изменения туда **не пишем**.

2. **Совместимость с существующими данными.** Таблицы непустые (прод работает). Новая `NOT NULL` колонка без default сломает существующие строки — добавляй либо `nullable`, либо с `DEFAULT`/backfill. Сужение типа/ограничения — проверь, что текущие данные ему удовлетворяют.

3. **Создай ревизию.** `conda activate telegram_bot` → `alembic revision -m "краткое описание"`. Появится файл в `alembic/versions/` (имя по шаблону `ГГГГММДД_slug_rev`). Заполни `upgrade()` идемпотентным DDL через `op.execute(...)`:
   ```python
   def upgrade() -> None:
       op.execute(r"""
       DO $$ BEGIN
         IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                        WHERE table_name='...' AND column_name='...') THEN
           ALTER TABLE ... ADD COLUMN ...;
         END IF;
       END $$;
       """)
   ```
   Для таблиц/ограничений/индексов — `CREATE TABLE/INDEX IF NOT EXISTS`, проверка `pg_constraint` в `DO $$ … $$`. `down_revision` Alembic проставит сам — не трогай его вручную, следи, чтобы был ровно один head (`alembic heads`).

4. **Проверь «upgrade».** Прогони `alembic upgrade head` на тестовой БД (через `ALEMBIC_DATABASE_URL` на отдельную пустую/тестовую базу). Затем `alembic upgrade head` **повторно** — идемпотентность означает, что второй прогон не падает. Если БД/Docker недоступны — не запускай, опиши как ручной шаг.

5. **Заполни «downgrade».** В `downgrade()` напиши обратный DDL (`DROP COLUMN/TABLE/CONSTRAINT`, обычно тоже `IF EXISTS`). Оцени потерю данных при откате. Если откат деструктивен и нежелателен — `raise NotImplementedError(...)` с пояснением (как в baseline), но для обычных изменений предпочтителен рабочий downgrade.

6. **Server defaults.** Для новых колонок реши: `DEFAULT` на уровне БД (применится к существующим строкам сразу) или значение в коде. Зафиксируй выбор явно в комментарии ревизии.

7. **Nullable-переходы.** Переход `NULL → NOT NULL` делай в два шага внутри `upgrade()`: добавить nullable + backfill данных (`UPDATE ... WHERE ... IS NULL`), затем `ALTER COLUMN ... SET NOT NULL`. Не вешай NOT NULL на колонку, где уже есть NULL.

8. **Индексы и ограничения.** Нужны ли индексы под новые запросы (по `user_id`, `project_id`, датам). Уникальные ограничения — проверь, что текущие данные их не нарушают (иначе `ADD CONSTRAINT`/`CREATE UNIQUE INDEX` упадёт).

9. **Не редактируй применённые ревизии.** Уже выкаченные ревизии иммутабельны. Любое изменение — **новая** ревизия, не правка старой. Baseline (`0001_baseline`) не трогаем.

10. **Блокировки больших таблиц.** `ALTER TABLE`, добавление индекса/ограничения берут блокировку; на большой `expenses` это надолго заблокирует бота. Для индексов рассмотри `CREATE INDEX CONCURRENTLY` — но учти: `CONCURRENTLY` нельзя внутри транзакции, а Alembic по умолчанию оборачивает миграцию в транзакцию. Тогда добавь в ревизию `# transactional = False`-обход (отдельная ревизия без транзакции) или вынеси индекс ручным шагом. Оцени время и влияние на прод.

## Применение

- **Локально:** `alembic upgrade head` (conda `telegram_bot`). Диагностика: `alembic current`, `alembic history`, `alembic heads`.
- **Прод:** миграции применяются **автоматически при Docker-деплое** (одноразовый сервис `migrations` → `alembic upgrade head` до старта бота; см. `docker-compose.yml`, `.github/workflows/deploy.yml`). Вручную на сервере миграции не запускают.
- `alembic revision --autogenerate` на проде **не запускать никогда**.

## Вывод
Готовая ревизия в `alembic/versions/` (`upgrade()` + `downgrade()`) + краткая записка: что меняется, нужен ли backfill, риски блокировки, обратимость, ручные шаги. Применение к реальной БД и любой деструктивный SQL — **только с явного разрешения** (см. [CLAUDE.md](../../../CLAUDE.md)).
