from datetime import datetime
from unittest.mock import AsyncMock, patch

import pytest

from handlers.recommendations import recommendations_command
from recommendation.models import FinalRecommendation, RecommendationRequest
from recommendation.types import RecommendationType


@pytest.mark.asyncio
async def test_recommendations_command_sends_formatted_response(mock_update, mock_context):
    mock_context.user_data["active_project_id"] = None
    request = RecommendationRequest(
        user_id=str(mock_update.effective_user.id),
        requested_at=datetime(2026, 4, 21, 12, 0, 0),
    )
    generated = [
        FinalRecommendation(
            recommendation_id="r-1",
            source_rule_id="forecast_overspend",
            recommendation_type=RecommendationType.FORECAST_OVERSPEND,
            title="Риск перерасхода",
            message="Прогноз выше лимита.",
            score=80.0,
            rank=1,
        )
    ]

    fake_pipeline = AsyncMock()
    fake_pipeline.generate = AsyncMock(return_value=generated)

    with patch("handlers.recommendations._build_pipeline", return_value=fake_pipeline), patch(
        "handlers.recommendations._build_request", new=AsyncMock(return_value=request)
    ):
        await recommendations_command(mock_update, mock_context)

    mock_update.message.reply_text.assert_called_once()
    sent_text = mock_update.message.reply_text.call_args[0][0]
    assert "Риск перерасхода" in sent_text


@pytest.mark.asyncio
async def test_recommendations_command_handles_empty_result(mock_update, mock_context):
    request = RecommendationRequest(
        user_id=str(mock_update.effective_user.id),
        requested_at=datetime(2026, 4, 21, 12, 0, 0),
    )
    fake_pipeline = AsyncMock()
    fake_pipeline.generate = AsyncMock(return_value=[])

    with patch("handlers.recommendations._build_pipeline", return_value=fake_pipeline), patch(
        "handlers.recommendations._build_request", new=AsyncMock(return_value=request)
    ):
        await recommendations_command(mock_update, mock_context)

    mock_update.message.reply_text.assert_called_once()
    sent_text = mock_update.message.reply_text.call_args[0][0]
    assert "Пока нет устойчивых сигналов" in sent_text
