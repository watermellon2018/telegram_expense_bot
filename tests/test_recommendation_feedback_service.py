import pytest

from recommendation.feedback_service import RecommendationFeedbackService
from recommendation.repositories.in_memory import InMemoryFeedbackRepository
from recommendation.types import RecommendationFeedbackActionType


@pytest.mark.asyncio
async def test_feedback_service_write_and_read():
    repository = InMemoryFeedbackRepository()
    service = RecommendationFeedbackService(repository)

    saved = await service.add_feedback_event(
        recommendation_id="rec-svc-1",
        user_id="u-svc-1",
        action_type=RecommendationFeedbackActionType.SHOWN,
        metadata_json={"rank": 2},
    )
    await service.add_feedback_event(
        recommendation_id="rec-svc-1",
        user_id="u-svc-1",
        action_type=RecommendationFeedbackActionType.LIKED,
    )

    assert saved.id is not None

    rec_history = await service.get_feedback_for_recommendation("rec-svc-1")
    user_history = await service.get_feedback_for_user("u-svc-1")

    assert len(rec_history) == 2
    assert len(user_history) == 2
    assert rec_history[0].action_type == RecommendationFeedbackActionType.LIKED

