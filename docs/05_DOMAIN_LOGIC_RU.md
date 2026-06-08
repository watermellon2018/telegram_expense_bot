# 5. Предметная логика (Domain)

## 5.1. Расходы (`utils/excel.py`)

Несмотря на имя файла, модуль работает с PostgreSQL.

Ключевые операции:

- `add_expense`
  - проверяет права для project scope;
  - валидирует `category_id`;
  - вставляет запись в `expenses`.

- `get_month_expenses`
  - personal mode: только расходы пользователя;
  - project mode: агрегирует расходы всех участников проекта.

- `get_day_expenses`, `get_category_expenses`, `get_all_expenses`
  - поддерживают project/personal режимы;
  - применяют permission checks для project scope.

## 5.2. Категории расходов (`utils/categories.py`)

Функции:

- получение категорий по пользователю/проекту;
- создание пользовательских категорий;
- деактивация и удаление с переносом операций;
- гарантия системных категорий.

Принцип:

- системные категории доступны всегда;
- пользовательские категории изолированы по scope.

## 5.3. Доходы (`utils/incomes.py`, `utils/income_categories.py`)

### Доходы

- `add_income` добавляет фактическую запись дохода.
- `get_month_incomes`/`get_day_incomes`/`get_all_incomes` аналогичны расходной модели.
- `get_yearly_income_vs_expense` возвращает помесячный баланс доход/расход.

### Категории доходов

- отдельная таблица `income_categories`;
- те же принципы scoped категорий и `is_system/is_active`.

## 5.4. Проекты и совместная работа (`utils/projects.py`)

### Основные сценарии

- создание проекта + автодобавление owner в `project_members`;
- выбор активного проекта (`users.active_project_id`);
- вывод статистики проекта по всем участникам;
- soft-delete проекта через `deleted_at`.

### Инвайты

- создание токена приглашения (`project_invites`);
- срок действия по `expires_at`;
- принятие инвайта выполняется транзакционно:
  - добавить участника,
  - обновить `active_project_id`,
  - удалить токен.

### Управление ролями

- смена роли участника (owner only);
- удаление участника;
- выход участника из проекта;
- owner не может «просто выйти» из проекта.

## 5.5. RBAC (`utils/permissions.py`)

Роли:

- `owner`
- `editor`
- `viewer`

Права группируются по областям:

- project management;
- expense/category operations;
- view operations;
- budget operations.

Правило:

- при `project_id=None` операции считаются личными и разрешены.

## 5.6. Бюджеты (`utils/budgets.py`, `handlers/budget.py`, `utils/budget_notifier.py`)

### Хранение

- месячные бюджеты (личные и проектные);
- пороговые уведомления и флаги отправки.

### Логика

- наследование бюджета с прошлого месяца (`get_or_inherit_budget`);
- `set_budget` сбрасывает notification state при изменении суммы;
- отдельная настройка включения/выключения уведомлений.

### Уведомления

- планировщик каждые 4 часа;
- события:
  - threshold reached;
  - overspent;
- отправка один раз за месяц по каждому типу события;
- для project budget уведомляются все участники проекта.

## 5.7. Recurring расходы и доходы

### Расходы (`utils/recurring.py`, `handlers/recurring.py`)

- поддержка периодичностей:
  - daily,
  - every_n_days,
  - weekly,
  - every_n_weeks,
  - monthly,
  - every_n_months.

- детерминированный расчет следующей даты `calculate_next_run`.
- воркер каждые 5 минут:
  - выбирает due active rules;
  - проверяет идемпотентность (нет ли записи за сегодня);
  - создает расход;
  - обновляет `next_run_at`.

### Доходы (`utils/recurring_incomes.py`, `handlers/recurring_income.py`)

Симметричная модель:

- те же frequency patterns;
- тот же принцип идемпотентности;
- вставка в `incomes` + пересчет `next_run_at`.

### Pattern detector (`utils/pattern_detector.py`)

- без ML;
- эвристика на повторяемости суммы/интервалов/комментария;
- cooldown, чтобы не спамить предложениями recurring-правила.

## 5.8. Cashback (`utils/cashback.py`, `handlers/cashback.py`)

MVP-подход:

- считается только теоретический cashback;
- матчинги по названию категории;
- возможна разница с фактическим банковским начислением.

Компоненты:

- карты пользователя (`user_cards`);
- cashback categories (global/custom);
- cashback rules по месяцу;
- расчет summary за период;
- агрегат за последние 12 месяцев.

Особенность:

- для закрытых месяцев личного контура используется `cashback_monthly_snapshots` (immutable snapshot).
