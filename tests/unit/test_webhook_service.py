"""Tests for webhook_service.py and the webhook registration endpoint"""

from unittest.mock import AsyncMock, Mock, patch
from uuid import uuid4

import httpx
import pytest
from fastapi import HTTPException

from api.routes.webhooks import register_webhook
from api.schemas.review import WebhookRegister
from core.services.webhook_service import deliver_webhook


@pytest.mark.unit
class TestDeliverWebhook:
    """Test suite for deliver_webhook()."""

    @pytest.mark.asyncio
    async def test_returns_true_on_2xx_response(self):
        mock_response = Mock()
        mock_response.is_success = True
        mock_response.status_code = 200

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("core.services.webhook_service.httpx.AsyncClient", return_value=mock_client):
            result = await deliver_webhook(
                "http://127.0.0.1:9999/hook", {"id": "abc", "status": "complete"}, "abc"
            )

        assert result is True
        mock_client.post.assert_called_once_with(
            "http://127.0.0.1:9999/hook", json={"id": "abc", "status": "complete"}
        )

    @pytest.mark.asyncio
    async def test_returns_false_on_non_2xx_response(self):
        mock_response = Mock()
        mock_response.is_success = False
        mock_response.status_code = 500

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("core.services.webhook_service.httpx.AsyncClient", return_value=mock_client):
            result = await deliver_webhook(
                "http://127.0.0.1:9999/hook", {"id": "abc", "status": "complete"}, "abc"
            )

        assert result is False

    @pytest.mark.asyncio
    async def test_returns_false_and_does_not_raise_on_timeout(self):
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(side_effect=httpx.TimeoutException("timed out"))
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("core.services.webhook_service.httpx.AsyncClient", return_value=mock_client):
            result = await deliver_webhook(
                "http://127.0.0.1:9999/hook", {"id": "abc", "status": "complete"}, "abc"
            )

        assert result is False

    @pytest.mark.asyncio
    async def test_returns_false_and_does_not_raise_on_connection_error(self):
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(side_effect=httpx.ConnectError("connection refused"))
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("core.services.webhook_service.httpx.AsyncClient", return_value=mock_client):
            result = await deliver_webhook(
                "http://127.0.0.1:9999/hook", {"id": "abc", "status": "complete"}, "abc"
            )

        assert result is False


@pytest.mark.unit
class TestRegisterWebhook:
    """Test suite for the POST /reviews/{review_id}/webhooks endpoint."""

    @pytest.fixture
    def mock_db_session(self):
        session = AsyncMock()
        session.add = Mock()
        return session

    @pytest.fixture
    def current_user(self):
        user = Mock()
        user.id = str(uuid4())
        return user

    @pytest.fixture
    def data(self):
        return WebhookRegister(callback_url="http://127.0.0.1:9999/hook")

    def _review(self, status):
        review = Mock()
        review.id = uuid4()
        review.status = status
        return review

    @pytest.mark.asyncio
    async def test_delivers_immediately_when_review_already_complete(
        self, mock_db_session, current_user, data
    ):
        """Registering after completion fires the POST from the registration call."""
        review = self._review("complete")

        with (
            patch("api.routes.webhooks.get_review", new=AsyncMock(return_value=review)),
            patch("api.routes.webhooks.ReviewResponse") as MockReviewResponse,
            patch("api.routes.webhooks.deliver_webhook", new=AsyncMock()) as mock_deliver,
        ):
            MockReviewResponse.model_validate.return_value.model_dump.return_value = {
                "status": "complete"
            }
            await register_webhook(review.id, data, current_user, mock_db_session)

        assert review.callback_url == "http://127.0.0.1:9999/hook"
        mock_db_session.commit.assert_awaited_once()
        mock_db_session.refresh.assert_awaited_once_with(review)
        mock_deliver.assert_awaited_once_with(
            "http://127.0.0.1:9999/hook", {"status": "complete"}, str(review.id)
        )

    @pytest.mark.asyncio
    async def test_stores_without_delivering_when_review_not_terminal(
        self, mock_db_session, current_user, data
    ):
        """Registering before completion only stores the URL for process_review()."""
        review = self._review("processing")

        with (
            patch("api.routes.webhooks.get_review", new=AsyncMock(return_value=review)),
            patch("api.routes.webhooks.ReviewResponse"),
            patch("api.routes.webhooks.deliver_webhook", new=AsyncMock()) as mock_deliver,
        ):
            await register_webhook(review.id, data, current_user, mock_db_session)

        assert review.callback_url == "http://127.0.0.1:9999/hook"
        mock_db_session.commit.assert_awaited_once()
        mock_deliver.assert_not_called()

    @pytest.mark.asyncio
    async def test_returns_404_when_review_not_found(self, mock_db_session, current_user, data):
        """An unknown or unowned review is a 404 and nothing is stored."""
        with (
            patch("api.routes.webhooks.get_review", new=AsyncMock(return_value=None)),
            patch("api.routes.webhooks.deliver_webhook", new=AsyncMock()) as mock_deliver,
            pytest.raises(HTTPException) as exc_info,
        ):
            await register_webhook(uuid4(), data, current_user, mock_db_session)

        assert exc_info.value.status_code == 404
        mock_db_session.commit.assert_not_called()
        mock_deliver.assert_not_called()
