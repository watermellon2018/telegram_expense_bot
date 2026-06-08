"""
PostgreSQL repository for monthly analytics summaries.
"""

from typing import List, Optional, Sequence

from recommendation.models import MonthlyCategorySummary, MonthlyUserSummary
from utils import db


class PostgresMonthlySummaryRepository:
    """CRUD helpers for monthly summary tables."""

    async def upsert_monthly_user_summary(
        self,
        summary: MonthlyUserSummary,
    ) -> MonthlyUserSummary:
        row = await db.fetchrow(
            """
            INSERT INTO monthly_user_summary (
                user_id,
                month_key,
                total_expense_full,
                total_income_full,
                net_balance_full,
                tx_count,
                avg_check,
                median_check,
                recurring_amount_full,
                recurring_share_full,
                small_expense_amount_full,
                small_expense_share_full,
                total_expense_baseline_adjusted,
                recurring_amount_baseline_adjusted
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14)
            ON CONFLICT (user_id, month_key) DO UPDATE SET
                total_expense_full = EXCLUDED.total_expense_full,
                total_income_full = EXCLUDED.total_income_full,
                net_balance_full = EXCLUDED.net_balance_full,
                tx_count = EXCLUDED.tx_count,
                avg_check = EXCLUDED.avg_check,
                median_check = EXCLUDED.median_check,
                recurring_amount_full = EXCLUDED.recurring_amount_full,
                recurring_share_full = EXCLUDED.recurring_share_full,
                small_expense_amount_full = EXCLUDED.small_expense_amount_full,
                small_expense_share_full = EXCLUDED.small_expense_share_full,
                total_expense_baseline_adjusted = EXCLUDED.total_expense_baseline_adjusted,
                recurring_amount_baseline_adjusted = EXCLUDED.recurring_amount_baseline_adjusted,
                updated_at = NOW()
            RETURNING
                id,
                user_id,
                month_key,
                total_expense_full,
                total_income_full,
                net_balance_full,
                tx_count,
                avg_check,
                median_check,
                recurring_amount_full,
                recurring_share_full,
                small_expense_amount_full,
                small_expense_share_full,
                total_expense_baseline_adjusted,
                recurring_amount_baseline_adjusted,
                created_at,
                updated_at
            """,
            summary.user_id,
            summary.month_key,
            summary.total_expense_full,
            summary.total_income_full,
            summary.net_balance_full,
            summary.tx_count,
            summary.avg_check,
            summary.median_check,
            summary.recurring_amount_full,
            summary.recurring_share_full,
            summary.small_expense_amount_full,
            summary.small_expense_share_full,
            summary.total_expense_baseline_adjusted,
            summary.recurring_amount_baseline_adjusted,
        )
        if row is None:
            return summary
        return self._row_to_monthly_user_summary(row)

    async def get_monthly_user_summary(
        self,
        user_id: str,
        month_key: str,
    ) -> Optional[MonthlyUserSummary]:
        row = await db.fetchrow(
            """
            SELECT
                id,
                user_id,
                month_key,
                total_expense_full,
                total_income_full,
                net_balance_full,
                tx_count,
                avg_check,
                median_check,
                recurring_amount_full,
                recurring_share_full,
                small_expense_amount_full,
                small_expense_share_full,
                total_expense_baseline_adjusted,
                recurring_amount_baseline_adjusted,
                created_at,
                updated_at
            FROM monthly_user_summary
            WHERE user_id = $1 AND month_key = $2
            """,
            user_id,
            month_key,
        )
        if row is None:
            return None
        return self._row_to_monthly_user_summary(row)

    async def upsert_monthly_category_summaries(
        self,
        summaries: Sequence[MonthlyCategorySummary],
    ) -> Sequence[MonthlyCategorySummary]:
        persisted: List[MonthlyCategorySummary] = []
        for summary in summaries:
            row = await db.fetchrow(
                """
                INSERT INTO monthly_category_summary (
                    user_id,
                    month_key,
                    category_id,
                    total_amount_full,
                    total_amount_baseline_adjusted,
                    tx_count,
                    share_in_month
                )
                VALUES ($1, $2, $3, $4, $5, $6, $7)
                ON CONFLICT (user_id, month_key, category_id) DO UPDATE SET
                    total_amount_full = EXCLUDED.total_amount_full,
                    total_amount_baseline_adjusted = EXCLUDED.total_amount_baseline_adjusted,
                    tx_count = EXCLUDED.tx_count,
                    share_in_month = EXCLUDED.share_in_month,
                    updated_at = NOW()
                RETURNING
                    id,
                    user_id,
                    month_key,
                    category_id,
                    total_amount_full,
                    total_amount_baseline_adjusted,
                    tx_count,
                    share_in_month,
                    created_at,
                    updated_at
                """,
                summary.user_id,
                summary.month_key,
                summary.category_id,
                summary.total_amount_full,
                summary.total_amount_baseline_adjusted,
                summary.tx_count,
                summary.share_in_month,
            )
            if row is None:
                continue
            persisted.append(self._row_to_monthly_category_summary(row))
        return persisted

    async def get_monthly_category_summaries(
        self,
        user_id: str,
        month_key: str,
    ) -> Sequence[MonthlyCategorySummary]:
        rows = await db.fetch(
            """
            SELECT
                id,
                user_id,
                month_key,
                category_id,
                total_amount_full,
                total_amount_baseline_adjusted,
                tx_count,
                share_in_month,
                created_at,
                updated_at
            FROM monthly_category_summary
            WHERE user_id = $1 AND month_key = $2
            ORDER BY total_amount_full DESC, category_id ASC
            """,
            user_id,
            month_key,
        )
        return [self._row_to_monthly_category_summary(row) for row in rows]

    @staticmethod
    def _row_to_monthly_user_summary(row) -> MonthlyUserSummary:
        return MonthlyUserSummary(
            id=int(row["id"]),
            user_id=str(row["user_id"]),
            month_key=str(row["month_key"]),
            total_expense_full=float(row["total_expense_full"]),
            total_income_full=float(row["total_income_full"]),
            net_balance_full=float(row["net_balance_full"]),
            tx_count=int(row["tx_count"]),
            avg_check=float(row["avg_check"]),
            median_check=float(row["median_check"]),
            recurring_amount_full=float(row["recurring_amount_full"]),
            recurring_share_full=float(row["recurring_share_full"]),
            small_expense_amount_full=float(row["small_expense_amount_full"]),
            small_expense_share_full=float(row["small_expense_share_full"]),
            total_expense_baseline_adjusted=float(row["total_expense_baseline_adjusted"]),
            recurring_amount_baseline_adjusted=float(row["recurring_amount_baseline_adjusted"]),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    @staticmethod
    def _row_to_monthly_category_summary(row) -> MonthlyCategorySummary:
        return MonthlyCategorySummary(
            id=int(row["id"]),
            user_id=str(row["user_id"]),
            month_key=str(row["month_key"]),
            category_id=int(row["category_id"]),
            total_amount_full=float(row["total_amount_full"]),
            total_amount_baseline_adjusted=float(row["total_amount_baseline_adjusted"]),
            tx_count=int(row["tx_count"]),
            share_in_month=float(row["share_in_month"]),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

