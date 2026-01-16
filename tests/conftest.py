"""
Pytest configuration and shared fixtures
"""
import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, Mock
from telegram import Update, User, Message, Chat, CallbackQuery
from telegram.ext import ContextTypes


@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def mock_user():
    """Создает mock пользователя Telegram"""
    user = Mock(spec=User)
    user.id = 123456789
    user.first_name = "Test"
    user.last_name = "User"
    user.username = "testuser"
    user.is_bot = False
    return user


@pytest.fixture
def mock_chat():
    """Создает mock чата"""
    chat = Mock(spec=Chat)
    chat.id = 123456789
    chat.type = "private"
    return chat


@pytest.fixture
def mock_message(mock_user, mock_chat):
    """Создает mock сообщения"""
    message = AsyncMock(spec=Message)
    message.from_user = mock_user
    message.chat = mock_chat
    message.message_id = 1
    message.text = "/start"
    message.reply_text = AsyncMock()
    message.reply_photo = AsyncMock()
    message.reply_document = AsyncMock()
    return message


@pytest.fixture
def mock_callback_query(mock_user, mock_message):
    """Создает mock callback query"""
    query = AsyncMock(spec=CallbackQuery)
    query.from_user = mock_user
    query.message = mock_message
    query.data = "test:data"
    query.answer = AsyncMock()
    query.edit_message_text = AsyncMock()
    query.delete_message = AsyncMock()
    return query


@pytest.fixture
def mock_update(mock_message):
    """Создает mock Update объект"""
    update = Mock(spec=Update)
    update.effective_user = mock_message.from_user
    update.effective_chat = mock_message.chat
    update.message = mock_message
    update.callback_query = None
    update.update_id = 1
    return update


@pytest.fixture
def mock_update_with_callback(mock_callback_query):
    """Создает mock Update с callback query"""
    update = Mock(spec=Update)
    update.effective_user = mock_callback_query.from_user
    update.effective_chat = mock_callback_query.message.chat
    update.message = None
    update.callback_query = mock_callback_query
    update.update_id = 1
    return update


@pytest.fixture
def mock_context():
    """Создает mock контекст бота"""
    context = Mock(spec=ContextTypes.DEFAULT_TYPE)
    context.bot = AsyncMock()
    context.user_data = {}
    context.chat_data = {}
    context.args = []
    return context


@pytest.fixture
def test_user_id():
    """Тестовый ID пользователя"""
    return 123456789


@pytest.fixture
def test_project_id():
    """Тестовый ID проекта"""
    return 1
