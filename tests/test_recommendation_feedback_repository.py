import pytest

from recommendation.models import RecommendationFeedback
from recommendation.repositories.in_memory import InMemoryFeedbackRepository
from recommendation.types import RecommendationFeedbackActionType


@pytest.mark.asyncio
async def test_feedback_repository_store_and_fetch_by_recommendation_and_user():
    repository = InMemoryFeedbackRepository()

    event_1 = await repository.save_feedback(
        RecommendationFeedback(
            recommendation_id="rec-1",
            user_id="u-1",
            action_type=RecommendationFeedbackActionType.SHOWN,
            metadata_json={"rank": 1},
        )
    )
    event_2 = await repository.save_feedback(
        RecommendationFeedback(
            recommendation_id="rec-1",
            user_id="u-1",
            action_type=RecommendationFeedbackActionType.LIKED,
            metadata_json={"source": "button"},
        )
    )
    await repository.save_feedback(
        RecommendationFeedback(
            recommendation_id="rec-2",
            user_id="u-2",
            action_type=RecommendationFeedbackActionType.DISMISSED,
        )
    )

    assert event_1.id is not None
    assert event_2.id is not None
    assert event_2.id > event_1.id

    by_rec = await repository.get_feedback_by_recommendation("rec-1")
    assert len(by_rec) == 2
    assert by_rec[0].action_type == RecommendationFeedbackActionType.LIKED

    by_user = await repository.get_feedback_by_user("u-1")
    assert len(by_user) == 2
    assert by_user[0].recommendation_id == "rec-1"

    compat = await repository.get_feedback(user_id="u-1", project_id=None, limit=10)
    assert len(compat) == 2

