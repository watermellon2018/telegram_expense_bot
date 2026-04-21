from datetime import datetime
from unittest.mock import AsyncMock, patch

import pytest

from recommendation.models import RecommendationFeedback
from recommendation.repositories.postgres import PostgresFeedbackRepository
from recommendation.types import RecommendationFeedbackActionType


@pytest.mark.asyncio
async def test_postgres_feedback_repository_save_event():
    repository = PostgresFeedbackRepository()
    now = datetime.utcnow()
    returned_row = {
        "id": 30,
        "recommendation_id": "rec-pg-1",
        "user_id": "u-pg-1",
        "action_type": "shown",
        "metadata_json": {"rank": 1},
        "created_at": now,
    }

    with patch(
        "recommendation.repositories.postgres.db.fetchrow",
        new=AsyncMock(return_value=returned_row),
    ):
        saved = await repository.save_feedback(
            RecommendationFeedback(
                recommendation_id="rec-pg-1",
                user_id="u-pg-1",
                action_type=RecommendationFeedbackActionType.SHOWN,
                created_at=now,
                metadata_json={"rank": 1},
            )
        )

    assert saved.id == 30
    assert saved.action_type == RecommendationFeedbackActionType.SHOWN


@pytest.mark.asyncio
async def test_postgres_feedback_repository_fetch_by_user_and_recommendation():
    repository = PostgresFeedbackRepository()
    now = datetime.utcnow()
    rows = [
        {
            "id": 31,
            "recommendation_id": "rec-pg-2",
            "user_id": "u-pg-2",
            "action_type": "opened_details",
            "metadata_json": {"screen": "details"},
            "created_at": now,
        }
    ]

    with patch(
        "recommendation.repositories.postgres.db.fetch",
        new=AsyncMock(return_value=rows),
    ):
        by_rec = await repository.get_feedback_by_recommendation("rec-pg-2")
        by_user = await repository.get_feedback_by_user("u-pg-2")

    assert len(by_rec) == 1
    assert by_rec[0].action_type == RecommendationFeedbackActionType.OPENED_DETAILS
    assert len(by_user) == 1
    assert by_user[0].recommendation_id == "rec-pg-2"

