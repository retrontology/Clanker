"""
Unit tests for DatabaseManager.

Tests database operations, connection handling, and error recovery.
"""

import pytest
import asyncio
from datetime import datetime, timedelta
from unittest.mock import Mock, AsyncMock, patch

from chatbot.database.operations import DatabaseManager, ChannelConfigManager
from chatbot.database.models import MessageEvent, Message, ChannelConfig
from tests.conftest import create_test_config, create_test_message


class TestDatabaseManager:
    """Test cases for DatabaseManager class."""
    
    @pytest.mark.asyncio
    async def test_initialization_sqlite(self, temp_db_file):
        """Test SQLite database initialization."""
        manager = DatabaseManager(db_type="sqlite", database_url=temp_db_file)
        result = await manager.initialize()
        
        assert result is True
        assert manager.db_type == "sqlite"
        assert manager.connection_params["database_url"] == temp_db_file
    
    @pytest.mark.asyncio
    async def test_initialization_mysql_config(self):
        """Test MySQL database configuration (without actual connection)."""
        manager = DatabaseManager(
            db_type="mysql",
            host="localhost",
            port=3306,
            user="testuser",
            password="testpass",
            database="testdb"
        )
        
        assert manager.db_type == "mysql"
        assert manager.connection_params["host"] == "localhost"
        assert manager.connection_params["port"] == 3306
        assert manager.connection_params["user"] == "testuser"
        assert manager.connection_params["password"] == "testpass"
        assert manager.connection_params["database"] == "testdb"
    
    @pytest.mark.asyncio
    async def test_store_message_success(self, db_manager, sample_message_event):
        """Test successful message storage."""
        result = await db_manager.store_message(sample_message_event)
        
        assert result is True
        
        # Verify message was stored
        messages = await db_manager.get_recent_messages(sample_message_event.channel, 10)
        assert len(messages) == 1
        assert messages[0].message_id == sample_message_event.message_id
        assert messages[0].content == sample_message_event.content
    
    @pytest.mark.asyncio
    async def test_store_duplicate_message(self, db_manager, sample_message_event):
        """Test storing duplicate message (should be ignored)."""
        # Store message twice
        result1 = await db_manager.store_message(sample_message_event)
        result2 = await db_manager.store_message(sample_message_event)
        
        assert result1 is True
        assert result2 is True
        
        # Should only have one message
        messages = await db_manager.get_recent_messages(sample_message_event.channel, 10)
        assert len(messages) == 1
    
    @pytest.mark.asyncio
    async def test_get_recent_messages_empty(self, db_manager):
        """Test getting messages from empty database."""
        messages = await db_manager.get_recent_messages("emptychannel", 10)
        assert messages == []
    
    @pytest.mark.asyncio
    async def test_get_recent_messages_with_limit(self, db_manager):
        """Test getting messages with limit."""
        channel = "testchannel"
        
        # Store multiple messages
        for i in range(5):
            event = MessageEvent(
                message_id=f"msg-{i}",
                channel=channel,
                user_id=f"user{i}",
                user_display_name=f"User{i}",
                content=f"Message {i}",
                timestamp=datetime.now() + timedelta(seconds=i),
                badges={}
            )
            await db_manager.store_message(event)
        
        # Get with limit
        messages = await db_manager.get_recent_messages(channel, 3)
        assert len(messages) == 3
        
        # Should be in chronological order (oldest first)
        assert messages[0].message_content == "Message 2"  # 3rd oldest
        assert messages[1].message_content == "Message 3"  # 2nd oldest
        assert messages[2].message_content == "Message 4"  # Most recent
    
    @pytest.mark.asyncio
    async def test_get_recent_messages_channel_isolation(self, db_manager):
        """Test that messages are isolated by channel."""
        # Store messages in different channels
        event1 = MessageEvent(
            message_id="msg-1",
            channel="channel1",
            user_id="user1",
            user_display_name="User1",
            content="Message in channel 1",
            timestamp=datetime.now(),
            badges={}
        )
        
        event2 = MessageEvent(
            message_id="msg-2",
            channel="channel2",
            user_id="user2",
            user_display_name="User2",
            content="Message in channel 2",
            timestamp=datetime.now(),
            badges={}
        )
        
        await db_manager.store_message(event1)
        await db_manager.store_message(event2)
        
        # Each channel should only see its own messages
        channel1_messages = await db_manager.get_recent_messages("channel1", 10)
        channel2_messages = await db_manager.get_recent_messages("channel2", 10)
        
        assert len(channel1_messages) == 1
        assert len(channel2_messages) == 1
        assert channel1_messages[0].content == "Message in channel 1"
        assert channel2_messages[0].content == "Message in channel 2"
    
    @pytest.mark.asyncio
    async def test_delete_message_by_id(self, db_manager, sample_message_event):
        """Test deleting a specific message by ID."""
        # Store message
        await db_manager.store_message(sample_message_event)
        
        # Verify it exists
        messages = await db_manager.get_recent_messages(sample_message_event.channel, 10)
        assert len(messages) == 1
        
        # Delete by ID
        result = await db_manager.delete_message_by_id(sample_message_event.message_id)
        assert result is True
        
        # Verify it's gone
        messages = await db_manager.get_recent_messages(sample_message_event.channel, 10)
        assert len(messages) == 0
    
    @pytest.mark.asyncio
    async def test_delete_user_messages(self, db_manager):
        """Test deleting all messages from a specific user."""
        channel = "testchannel"
        target_user = "baduser"
        
        # Store messages from different users
        for i in range(3):
            event = MessageEvent(
                message_id=f"msg-{i}",
                channel=channel,
                user_id=target_user if i < 2 else "gooduser",
                user_display_name=f"User{i}",
                content=f"Message {i}",
                timestamp=datetime.now() + timedelta(seconds=i),
                badges={}
            )
            await db_manager.store_message(event)
        
        # Delete messages from target user
        result = await db_manager.delete_user_messages(channel, target_user)
        assert result is True
        
        # Should only have message from good user
        messages = await db_manager.get_recent_messages(channel, 10)
        assert len(messages) == 1
        assert messages[0].user_id == "gooduser"
    
    @pytest.mark.asyncio
    async def test_clear_channel_messages(self, db_manager):
        """Test clearing all messages in a channel."""
        channel = "testchannel"
        
        # Store multiple messages
        for i in range(3):
            event = MessageEvent(
                message_id=f"msg-{i}",
                channel=channel,
                user_id=f"user{i}",
                user_display_name=f"User{i}",
                content=f"Message {i}",
                timestamp=datetime.now() + timedelta(seconds=i),
                badges={}
            )
            await db_manager.store_message(event)
        
        # Clear all messages
        result = await db_manager.clear_channel_messages(channel)
        assert result is True
        
        # Should be empty
        messages = await db_manager.get_recent_messages(channel, 10)
        assert len(messages) == 0
    
    @pytest.mark.asyncio
    async def test_cleanup_old_messages(self, db_manager):
        """Test cleaning up old messages based on retention policy."""
        channel = "testchannel"
        
        # Store old and new messages
        old_time = datetime.now() - timedelta(days=10)
        new_time = datetime.now() - timedelta(hours=1)
        
        old_event = MessageEvent(
            message_id="old-msg",
            channel=channel,
            user_id="user1",
            user_display_name="User1",
            content="Old message",
            timestamp=old_time,
            badges={}
        )
        
        new_event = MessageEvent(
            message_id="new-msg",
            channel=channel,
            user_id="user2",
            user_display_name="User2",
            content="New message",
            timestamp=new_time,
            badges={}
        )
        
        await db_manager.store_message(old_event)
        await db_manager.store_message(new_event)
        
        # Cleanup messages older than 7 days
        result = await db_manager.cleanup_old_messages(channel, retention_days=7)
        assert result is True
        
        # Should only have new message
        messages = await db_manager.get_recent_messages(channel, 10)
        assert len(messages) == 1
        assert messages[0].message_id == "new-msg"
    
    @pytest.mark.asyncio
    async def test_count_recent_messages(self, db_manager):
        """Test counting recent messages."""
        channel = "testchannel"
        
        # Store messages at different times
        old_time = datetime.now() - timedelta(hours=25)  # Older than 24 hours
        recent_time = datetime.now() - timedelta(hours=1)  # Within 24 hours
        
        old_event = MessageEvent(
            message_id="old-msg",
            channel=channel,
            user_id="user1",
            user_display_name="User1",
            content="Old message",
            timestamp=old_time,
            badges={}
        )
        
        for i in range(3):
            recent_event = MessageEvent(
                message_id=f"recent-msg-{i}",
                channel=channel,
                user_id=f"user{i+2}",
                user_display_name=f"User{i+2}",
                content=f"Recent message {i}",
                timestamp=recent_time + timedelta(minutes=i),
                badges={}
            )
            await db_manager.store_message(recent_event)
        
        await db_manager.store_message(old_event)
        
        # Count recent messages (last 24 hours)
        count = await db_manager.count_recent_messages(channel, hours=24)
        assert count == 3  # Only the recent messages
    
    @pytest.mark.asyncio
    async def test_health_check_success(self, db_manager):
        """Test successful health check."""
        result = await db_manager.health_check()
        assert result is True
        assert db_manager._connection_healthy is True
    
    @pytest.mark.asyncio
    async def test_connection_error_handling(self, temp_db_file):
        """Test connection error handling and retry logic."""
        manager = DatabaseManager(db_type="sqlite", database_url="/invalid/path/db.sqlite")
        
        # Should handle connection errors gracefully
        result = await manager.store_message(MessageEvent(
            message_id="test",
            channel="test",
            user_id="test",
            user_display_name="Test",
            content="Test",
            timestamp=datetime.now(),
            badges={}
        ))
        
        assert result is False  # Should fail gracefully
    
    @pytest.mark.asyncio
    async def test_get_connection_status(self, db_manager):
        """Test getting connection status information."""
        status = await db_manager.get_connection_status()
        
        assert isinstance(status, dict)
        assert 'db_type' in status
        assert 'connection_healthy' in status
        assert 'last_health_check' in status
        assert 'retry_count' in status
        assert status['db_type'] == 'sqlite'


class TestChannelConfigManager:
    """Test cases for ChannelConfigManager class."""
    
    @pytest.mark.asyncio
    async def test_get_config_creates_default(self, channel_config_manager):
        """Test that getting config creates default if not exists."""
        config = await channel_config_manager.get_config("newchannel")
        
        assert config.channel == "newchannel"
        assert config.message_threshold == 30  # Default value
        assert config.spontaneous_cooldown == 300  # Default value
        assert config.response_cooldown == 60  # Default value
        assert config.context_limit == 200  # Default value
    
    @pytest.mark.asyncio
    async def test_get_config_caching(self, channel_config_manager):
        """Test that configuration is cached properly."""
        # First call should create and cache
        config1 = await channel_config_manager.get_config("testchannel")
        
        # Second call should return cached version
        config2 = await channel_config_manager.get_config("testchannel")
        
        assert config1 is config2  # Same object reference
    
    @pytest.mark.asyncio
    async def test_update_config_success(self, channel_config_manager):
        """Test successful configuration update."""
        channel = "testchannel"
        
        # Update a setting
        result = await channel_config_manager.update_config(channel, "message_threshold", 50)
        assert result is True
        
        # Verify the update
        config = await channel_config_manager.get_config(channel)
        assert config.message_threshold == 50
    
    @pytest.mark.asyncio
    async def test_update_config_invalid_setting(self, channel_config_manager):
        """Test updating with invalid setting value."""
        channel = "testchannel"
        
        # Try to update with invalid value (negative threshold)
        result = await channel_config_manager.update_config(channel, "message_threshold", -5)
        assert result is False
    
    @pytest.mark.asyncio
    async def test_increment_message_count(self, channel_config_manager):
        """Test incrementing message count."""
        channel = "testchannel"
        
        # Initial count should be 0
        config = await channel_config_manager.get_config(channel)
        assert config.message_count == 0
        
        # Increment count
        new_count = await channel_config_manager.increment_message_count(channel)
        assert new_count == 1
        
        # Verify in config
        config = await channel_config_manager.get_config(channel)
        assert config.message_count == 1
    
    @pytest.mark.asyncio
    async def test_reset_message_count(self, channel_config_manager):
        """Test resetting message count."""
        channel = "testchannel"
        
        # Set count to non-zero
        await channel_config_manager.increment_message_count(channel)
        await channel_config_manager.increment_message_count(channel)
        
        config = await channel_config_manager.get_config(channel)
        assert config.message_count == 2
        
        # Reset count
        await channel_config_manager.reset_message_count(channel)
        
        # Verify reset
        config = await channel_config_manager.get_config(channel)
        assert config.message_count == 0
    
    @pytest.mark.asyncio
    async def test_spontaneous_cooldown_logic(self, channel_config_manager):
        """Test spontaneous message cooldown logic."""
        channel = "testchannel"
        
        # Initially should be able to generate
        can_generate = await channel_config_manager.can_generate_spontaneous(channel)
        assert can_generate is False  # False because message count is 0
        
        # Set message count to threshold
        config = await channel_config_manager.get_config(channel)
        for _ in range(config.message_threshold):
            await channel_config_manager.increment_message_count(channel)
        
        # Now should be able to generate
        can_generate = await channel_config_manager.can_generate_spontaneous(channel)
        assert can_generate is True
        
        # Update timestamp (simulate message sent)
        await channel_config_manager.update_spontaneous_timestamp(channel)
        
        # Should not be able to generate immediately (cooldown active)
        can_generate = await channel_config_manager.can_generate_spontaneous(channel)
        assert can_generate is False
    
    @pytest.mark.asyncio
    async def test_user_response_cooldown(self, channel_config_manager):
        """Test per-user response cooldown logic."""
        channel = "testchannel"
        user_id = "12345"
        
        # Initially should be able to respond
        can_respond = await channel_config_manager.can_respond_to_user(channel, user_id)
        assert can_respond is True
        
        # Update response timestamp
        await channel_config_manager.update_user_response_timestamp(channel, user_id)
        
        # Should not be able to respond immediately (cooldown active)
        can_respond = await channel_config_manager.can_respond_to_user(channel, user_id)
        assert can_respond is False
    
    @pytest.mark.asyncio
    async def test_config_validation(self, channel_config_manager):
        """Test configuration value validation."""
        channel = "testchannel"
        
        # Valid values should work
        assert await channel_config_manager.update_config(channel, "message_threshold", 50) is True
        assert await channel_config_manager.update_config(channel, "spontaneous_cooldown", 600) is True
        
        # Invalid values should be rejected
        assert await channel_config_manager.update_config(channel, "message_threshold", 0) is False
        assert await channel_config_manager.update_config(channel, "message_threshold", 2000) is False
        assert await channel_config_manager.update_config(channel, "spontaneous_cooldown", -1) is False