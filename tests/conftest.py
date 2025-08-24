"""
Pytest configuration and shared fixtures for the test suite.
"""

import pytest
import asyncio
import tempfile
import os
from datetime import datetime, timedelta
from typing import Dict, Any, List
from unittest.mock import Mock, AsyncMock, MagicMock

from chatbot.database.models import Message, MessageEvent, ChannelConfig
from chatbot.database.operations import DatabaseManager, ChannelConfigManager
from chatbot.ollama.client import OllamaClient
from chatbot.processing.filters import ContentFilter
from chatbot.config.commands import ConfigurationManager


@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def temp_db_file():
    """Create a temporary database file for testing."""
    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
        temp_path = f.name
    yield temp_path
    # Cleanup
    if os.path.exists(temp_path):
        os.unlink(temp_path)


@pytest.fixture
def temp_blocked_words_file():
    """Create a temporary blocked words file for testing."""
    content = """# Test blocked words file
# Comments are ignored
badword1
badword2
inappropriate phrase
# Category: Hate speech
slur1
slur2
"""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
        f.write(content)
        temp_path = f.name
    yield temp_path
    # Cleanup
    if os.path.exists(temp_path):
        os.unlink(temp_path)


@pytest.fixture
async def db_manager(temp_db_file):
    """Create a test database manager with SQLite."""
    manager = DatabaseManager(db_type="sqlite", database_url=temp_db_file)
    await manager.initialize()
    yield manager
    await manager.close() if hasattr(manager, 'close') else None


@pytest.fixture
async def channel_config_manager(db_manager):
    """Create a test channel configuration manager."""
    return ChannelConfigManager(db_manager)


@pytest.fixture
def mock_ollama_client():
    """Create a mock Ollama client for testing."""
    client = Mock(spec=OllamaClient)
    client.base_url = "http://localhost:11434"
    client.timeout = 30
    
    # Mock async methods
    client.list_available_models = AsyncMock(return_value=["llama3.1", "codellama", "mistral"])
    client.validate_model = AsyncMock(return_value=True)
    client.validate_startup_model = AsyncMock()
    client.is_service_available = AsyncMock(return_value=True)
    client.validate_model_for_command = AsyncMock(return_value=(True, ""))
    client.generate_spontaneous_message = AsyncMock(return_value="Test generated message")
    client.generate_response_message = AsyncMock(return_value="Test response message")
    client.should_skip_generation = Mock(return_value=False)
    client.get_service_status = Mock(return_value={
        'state': 'healthy',
        'consecutive_failures': 0,
        'base_url': 'http://localhost:11434'
    })
    
    return client


@pytest.fixture
def content_filter(temp_blocked_words_file):
    """Create a content filter with test blocked words."""
    return ContentFilter(temp_blocked_words_file)


@pytest.fixture
async def configuration_manager(channel_config_manager, mock_ollama_client):
    """Create a configuration manager for testing."""
    return ConfigurationManager(channel_config_manager, mock_ollama_client)


@pytest.fixture
def sample_message_event():
    """Create a sample MessageEvent for testing."""
    return MessageEvent(
        message_id="test-msg-123",
        channel="testchannel",
        user_id="12345",
        user_display_name="TestUser",
        content="Hello everyone!",
        timestamp=datetime.now(),
        badges={"subscriber": "1"}
    )


@pytest.fixture
def sample_messages():
    """Create a list of sample messages for testing."""
    base_time = datetime.now() - timedelta(minutes=10)
    messages = []
    
    for i in range(5):
        messages.append(Message(
            id=i + 1,
            message_id=f"msg-{i+1}",
            channel="testchannel",
            user_id=f"user{i+1}",
            user_display_name=f"User{i+1}",
            message_content=f"Test message {i+1}",
            timestamp=base_time + timedelta(minutes=i)
        ))
    
    return messages


@pytest.fixture
def moderator_badges():
    """Create moderator badges for testing."""
    return {"moderator": "1"}


@pytest.fixture
def broadcaster_badges():
    """Create broadcaster badges for testing."""
    return {"broadcaster": "1"}


@pytest.fixture
def regular_user_badges():
    """Create regular user badges for testing."""
    return {"subscriber": "1"}


@pytest.fixture
def mock_twitchio_message():
    """Create a mock TwitchIO message object."""
    message = Mock()
    message.id = "test-msg-123"
    message.content = "Hello everyone!"
    message.channel.name = "testchannel"
    
    # Mock author
    message.author = Mock()
    message.author.id = "12345"
    message.author.display_name = "TestUser"
    message.author.badges = {"subscriber": "1"}
    
    return message


@pytest.fixture
def mock_database_error():
    """Create a mock database error for testing error handling."""
    return Exception("Database connection failed")


@pytest.fixture
def mock_ollama_error():
    """Create a mock Ollama error for testing error handling."""
    from chatbot.ollama.client import OllamaError
    return OllamaError("Ollama service unavailable")


@pytest.fixture
def mock_timeout_error():
    """Create a mock timeout error for testing."""
    return asyncio.TimeoutError("Request timed out")


# Helper functions for tests
def create_test_config(channel: str = "testchannel", **overrides) -> ChannelConfig:
    """Create a test channel configuration with optional overrides."""
    defaults = {
        'channel': channel,
        'message_threshold': 30,
        'spontaneous_cooldown': 300,
        'response_cooldown': 60,
        'context_limit': 200,
        'ollama_model': None,
        'message_count': 0,
        'last_spontaneous_message': None,
        'created_at': datetime.now(),
        'updated_at': datetime.now()
    }
    defaults.update(overrides)
    return ChannelConfig(**defaults)


def create_test_message(message_id: str = "test-msg", channel: str = "testchannel", 
                       user_id: str = "12345", content: str = "Test message") -> Message:
    """Create a test message with optional overrides."""
    return Message(
        id=1,
        message_id=message_id,
        channel=channel,
        user_id=user_id,
        user_display_name="TestUser",
        message_content=content,
        timestamp=datetime.now()
    )