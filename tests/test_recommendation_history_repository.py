import pytest

from recommendation.models import RecommendationHistoryEntry
from recommendation.repositories.in_memory import InMemoryHistoryRepository
from recommendation.types import RecommendationHistoryStatus, RecommendationType


@pytest.mark.asyncio
async def test_history_repository_insert_and_query_by_period():
    repository = InMemoryHistoryRepository()

    inserted = await repository.insert_generated(
        [
            RecommendationHistoryEntry(
                id=None,
                user_id="u1",
                recommendation_type=RecommendationType.FORECAST_OVERSPEND,
                period_key="2026-04",
                entity_type="month",
                entity_id="2026-04",
                payload_json={"source_rule_id": "r1", "project_id": None},
                score=0.7,
            ),
            RecommendationHistoryEntry(
                id=None,
                user_id="u1",
                recommendation_type=RecommendationType.CASHBACK_OPPORTUNITY,
                period_key="2026-03",
                entity_type="category",
                entity_id="food",
                payload_json={"source_rule_id": "r2", "project_id": None},
                score=0.5,
            ),
            RecommendationHistoryEntry(
                id=None,
                user_id="u2",
                recommendation_type=RecommendationType.CASHBACK_OPPORTUNITY,
                period_key="2026-04",
                payload_json={},
                score=0.2,
            ),
        ]
    )

    assert len(inserted) == 3
    assert inserted[0].id is not None

    u1_april = await repository.get_recent_history("u1", period_key="2026-04")
    assert len(u1_april) == 1
    assert u1_april[0].recommendation_type == RecommendationType.FORECAST_OVERSPEND


@pytest.mark.asyncio
async def test_history_repository_mark_shown_and_compat_recent_records():
    repository = InMemoryHistoryRepository()
    inserted = await repository.insert_generated(
        [
            RecommendationHistoryEntry(
                id=None,
                user_id="u3",
                recommendation_type=RecommendationType.HIGH_RECURRING_SHARE,
                period_key="2026-04",
                payload_json={
                    "recommendation_id": "rec-1",
                    "source_rule_id": "rule-x",
                    "project_id": None,
                },
                score=0.9,
            )
        ]
    )

    updated = await repository.mark_as_shown([inserted[0].id])
    assert updated == 1

    history = await repository.get_recent_history("u3")
    assert history[0].status == RecommendationHistoryStatus.SHOWN
    assert history[0].shown_at is not None

    recent_records = await repository.get_recent("u3", project_id=None)
    assert len(recent_records) == 1
    assert recent_records[0].source_rule_id == "rule-x"
    assert recent_records[0].recommendation_id == "rec-1"

