"""
Integration tests for message processing flow.

Tests the complete flow from IRC message reception to generation and response.
"""

import pytest
import asyncio
from datetime import datetime, timedelta
from unittest.mock import Mock, AsyncMock, patch

from chatbot.database.operations import DatabaseManager, ChannelConfigManager
from chatbot.database.models import MessageEvent, Message
from chatbot.ollama.client import OllamaClient
from chatbot.processing.filters import ContentFilter
from chatbot.processing.coordinator import MessageProcessor
from chatbot.config.commands import ConfigurationManager
from chatbot.irc.client import TwitchIRCClient
from tests.conftest import create_test_config, create_test_message


class TestMessageProcessingFlow:
    """Integration tests for complete message processing flow."""
    
    @pytest.fixture
    async def message_processor(self, db_manager, temp_blocked_words_file):
        """Create a message processor with all dependencies."""
        # Create components
        content_filter = ContentFilter(temp_blocked_words_file)
        
        # Mock Ollama client
        ollama_client = Mock(spec=OllamaClient)
        ollama_client.generate_spontaneous_message = AsyncMock(return_value="Generated spontaneous message")
        ollama_client.generate_response_message = AsyncMock(return_value="Generated response message")
        ollama_client.should_skip_generation = Mock(return_value=False)
        
        # Mock IRC client
        irc_client = Mock(spec=TwitchIRCClient)
        irc_client.send_message = AsyncMock()
        
        # Create message processor
        from chatbot.processing.coordinator import MessageProcessor
        processor = MessageProcessor(db_manager, ollama_client, content_filter, irc_client)
        
        return processor
    
    @pytest.mark.asyncio
    async def test_complete_message_processing_flow(self, message_processor, db_manager):
        """Test complete flow from message reception to storage and potential generation."""
        channel = "testchannel"
        
        # Create a message event
        message_event = MessageEvent(
            message_id="test-msg-123",
            channel=channel,
            user_id="12345",
            user_display_name="TestUser",
            content="Hello everyone! This is a test message.",
            timestamp=datetime.now(),
            badges={"subscriber": "1"}
        )
        
        # Process the message
        await message_processor.process_incoming_message(message_event)
        
        # Verify message was stored
        messages = await db_manager.get_recent_messages(channel, 10)
        assert len(messages) == 1
        assert messages[0].message_id == "test-msg-123"
        assert messages[0].content == "Hello everyone! This is a test message."
    
    @pytest.mark.asyncio
    async def test_message_filtering_blocks_inappropriate_content(self, message_processor, db_manager):
        """Test that inappropriate content is filtered and not stored."""
        channel = "testchannel"
        
        # Create a message with blocked content
        message_event = MessageEvent(
            message_id="blocked-msg-123",
            channel=channel,
            user_id="12345",
            user_display_name="TestUser",
            content="This message contains badword1 and should be blocked",
            timestamp=datetime.now(),
            badges={}
        )
        
        # Process the message
        await message_processor.process_incoming_message(message_event)
        
        # Verify message was NOT stored
        messages = await db_manager.get_recent_messages(channel, 10)
        assert len(messages) == 0
    
    @pytest.mark.asyncio
    async def test_spontaneous_generation_trigger(self, message_processor, db_manager):
        """Test that spontaneous generation is triggered when threshold is reached."""
        channel = "testchannel"
        
        # Get channel config manager
        channel_config = ChannelConfigManager(db_manager)
        config = await channel_config.get_config(channel)
        
        # Store messages up to threshold
        for i in range(config.message_threshold):
            message_event = MessageEvent(
                message_id=f"msg-{i}",
                channel=channel,
                user_id=f"user{i}",
                user_display_name=f"User{i}",
                content=f"Test message {i}",
                timestamp=datetime.now() + timedelta(seconds=i),
                badges={}
            )
            await message_processor.process_incoming_message(message_event)
        
        # Verify generation was triggered
        message_processor.ollama_client.generate_spontaneous_message.assert_called()
        message_processor.irc_client.send_message.assert_called_with(channel, "Generated spontaneous message")
    
    @pytest.mark.asyncio
    async def test_mention_response_generation(self, message_processor, db_manager):
        """Test that mention responses are generated correctly."""
        channel = "testchannel"
        bot_username = "testbot"
        
        # Set bot username in processor
        message_processor.bot_username = bot_username
        
        # Create a mention message
        message_event = MessageEvent(
            message_id="mention-msg-123",
            channel=channel,
            user_id="12345",
            user_display_name="TestUser",
            content=f"@{bot_username} how are you doing?",
            timestamp=datetime.now(),
            badges={}
        )
        
        # Process the message
        await message_processor.process_incoming_message(message_event)
        
        # Verify response generation was triggered
        message_processor.ollama_client.generate_response_message.assert_called()
        message_processor.irc_client.send_message.assert_called_with(channel, "Generated response message")
    
    @pytest.mark.asyncio
    async def test_cooldown_prevents_generation(self, message_processor, db_manager):
        """Test that cooldowns prevent generation when active."""
        channel = "testchannel"
        
        # Get channel config and set recent spontaneous message
        channel_config = ChannelConfigManager(db_manager)
        await channel_config.update_spontaneous_timestamp(channel)
        
        # Reset mock call counts
        message_processor.ollama_client.generate_spontaneous_message.reset_mock()
        message_processor.irc_client.send_message.reset_mock()
        
        # Store messages up to threshold
        config = await channel_config.get_config(channel)
        for i in range(config.message_threshold):
            message_event = MessageEvent(
                message_id=f"cooldown-msg-{i}",
                channel=channel,
                user_id=f"user{i}",
                user_display_name=f"User{i}",
                content=f"Test message {i}",
                timestamp=datetime.now() + timedelta(seconds=i),
                badges={}
            )
            await message_processor.process_incoming_message(message_event)
        
        # Verify generation was NOT triggered due to cooldown
        message_processor.ollama_client.generate_spontaneous_message.assert_not_called()
        message_processor.irc_client.send_message.assert_not_called()
    
    @pytest.mark.asyncio
    async def test_user_response_cooldown(self, message_processor, db_manager):
        """Test that per-user response cooldowns work correctly."""
        channel = "testchannel"
        bot_username = "testbot"
        user_id = "12345"
        
        message_processor.bot_username = bot_username
        
        # First mention should generate response
        message_event1 = MessageEvent(
            message_id="mention-1",
            channel=channel,
            user_id=user_id,
            user_display_name="TestUser",
            content=f"@{bot_username} first question",
            timestamp=datetime.now(),
            badges={}
        )
        
        await message_processor.process_incoming_message(message_event1)
        
        # Verify first response was generated
        assert message_processor.ollama_client.generate_response_message.call_count == 1
        
        # Reset mocks
        message_processor.ollama_client.generate_response_message.reset_mock()
        message_processor.irc_client.send_message.reset_mock()
        
        # Second mention immediately after should be blocked by cooldown
        message_event2 = MessageEvent(
            message_id="mention-2",
            channel=channel,
            user_id=user_id,
            user_display_name="TestUser",
            content=f"@{bot_username} second question",
            timestamp=datetime.now(),
            badges={}
        )
        
        await message_processor.process_incoming_message(message_event2)
        
        # Verify second response was NOT generated due to cooldown
        message_processor.ollama_client.generate_response_message.assert_not_called()
        message_processor.irc_client.send_message.assert_not_called()
    
    @pytest.mark.asyncio
    async def test_moderation_event_cleanup(self, message_processor, db_manager):
        """Test that moderation events properly clean up stored messages."""
        channel = "testchannel"
        banned_user_id = "baduser123"
        
        # Store messages from different users
        for i, user_id in enumerate(["gooduser1", banned_user_id, "gooduser2", banned_user_id]):
            message_event = MessageEvent(
                message_id=f"msg-{i}",
                channel=channel,
                user_id=user_id,
                user_display_name=f"User{i}",
                content=f"Message from {user_id}",
                timestamp=datetime.now() + timedelta(seconds=i),
                badges={}
            )
            await message_processor.process_incoming_message(message_event)
        
        # Verify all messages were stored
        messages = await db_manager.get_recent_messages(channel, 10)
        assert len(messages) == 4
        
        # Simulate user ban (delete all messages from banned user)
        from chatbot.processing.coordinator import ModerationEvent
        mod_event = ModerationEvent(
            event_type="user_ban",
            channel=channel,
            user_id=banned_user_id,
            message_id=None
        )
        
        await message_processor.handle_moderation_event(mod_event)
        
        # Verify banned user's messages were removed
        messages = await db_manager.get_recent_messages(channel, 10)
        assert len(messages) == 2
        
        # Verify only good users' messages remain
        user_ids = [msg.user_id for msg in messages]
        assert "gooduser1" in user_ids
        assert "gooduser2" in user_ids
        assert banned_user_id not in user_ids
    
    @pytest.mark.asyncio
    async def test_single_message_deletion(self, message_processor, db_manager):
        """Test that single message deletion works correctly."""
        channel = "testchannel"
        
        # Store multiple messages
        message_ids = []
        for i in range(3):
            message_event = MessageEvent(
                message_id=f"msg-{i}",
                channel=channel,
                user_id=f"user{i}",
                user_display_name=f"User{i}",
                content=f"Message {i}",
                timestamp=datetime.now() + timedelta(seconds=i),
                badges={}
            )
            await message_processor.process_incoming_message(message_event)
            message_ids.append(f"msg-{i}")
        
        # Verify all messages were stored
        messages = await db_manager.get_recent_messages(channel, 10)
        assert len(messages) == 3
        
        # Delete specific message
        from chatbot.processing.coordinator import ModerationEvent
        mod_event = ModerationEvent(
            event_type="message_delete",
            channel=channel,
            user_id=None,
            message_id="msg-1"
        )
        
        await message_processor.handle_moderation_event(mod_event)
        
        # Verify only the specific message was removed
        messages = await db_manager.get_recent_messages(channel, 10)
        assert len(messages) == 2
        
        remaining_ids = [msg.message_id for msg in messages]
        assert "msg-0" in remaining_ids
        assert "msg-2" in remaining_ids
        assert "msg-1" not in remaining_ids
    
    @pytest.mark.asyncio
    async def test_channel_isolation(self, message_processor, db_manager):
        """Test that channels are properly isolated from each other."""
        channel1 = "channel1"
        channel2 = "channel2"
        
        # Store messages in different channels
        for channel in [channel1, channel2]:
            for i in range(3):
                message_event = MessageEvent(
                    message_id=f"{channel}-msg-{i}",
                    channel=channel,
                    user_id=f"user{i}",
                    user_display_name=f"User{i}",
                    content=f"Message {i} in {channel}",
                    timestamp=datetime.now() + timedelta(seconds=i),
                    badges={}
                )
                await message_processor.process_incoming_message(message_event)
        
        # Verify channel isolation
        channel1_messages = await db_manager.get_recent_messages(channel1, 10)
        channel2_messages = await db_manager.get_recent_messages(channel2, 10)
        
        assert len(channel1_messages) == 3
        assert len(channel2_messages) == 3
        
        # Verify messages are in correct channels
        for msg in channel1_messages:
            assert msg.channel == channel1
            assert channel1 in msg.content
        
        for msg in channel2_messages:
            assert msg.channel == channel2
            assert channel2 in msg.content
    
    @pytest.mark.asyncio
    async def test_ollama_unavailable_graceful_handling(self, message_processor, db_manager):
        """Test graceful handling when Ollama is unavailable."""
        channel = "testchannel"
        
        # Make Ollama unavailable
        message_processor.ollama_client.should_skip_generation.return_value = True
        message_processor.ollama_client.generate_spontaneous_message.return_value = None
        
        # Get channel config and store messages up to threshold
        channel_config = ChannelConfigManager(db_manager)
        config = await channel_config.get_config(channel)
        
        for i in range(config.message_threshold):
            message_event = MessageEvent(
                message_id=f"msg-{i}",
                channel=channel,
                user_id=f"user{i}",
                user_display_name=f"User{i}",
                content=f"Test message {i}",
                timestamp=datetime.now() + timedelta(seconds=i),
                badges={}
            )
            await message_processor.process_incoming_message(message_event)
        
        # Verify messages were still stored despite Ollama being unavailable
        messages = await db_manager.get_recent_messages(channel, 10)
        assert len(messages) == config.message_threshold
        
        # Verify no message was sent to IRC (due to Ollama unavailability)
        message_processor.irc_client.send_message.assert_not_called()
    
    @pytest.mark.asyncio
    async def test_context_window_management(self, message_processor, db_manager):
        """Test that context window is properly managed."""
        channel = "testchannel"
        
        # Get channel config and set a small context limit for testing
        channel_config = ChannelConfigManager(db_manager)
        await channel_config.update_config(channel, "context_limit", 5)
        
        # Store more messages than the context limit
        for i in range(10):
            message_event = MessageEvent(
                message_id=f"context-msg-{i}",
                channel=channel,
                user_id=f"user{i}",
                user_display_name=f"User{i}",
                content=f"Context message {i}",
                timestamp=datetime.now() + timedelta(seconds=i),
                badges={}
            )
            await message_processor.process_incoming_message(message_event)
        
        # Verify all messages were stored
        all_messages = await db_manager.get_recent_messages(channel, 20)
        assert len(all_messages) == 10
        
        # Verify context window respects the limit
        context_messages = await db_manager.get_recent_messages(channel, 5)
        assert len(context_messages) == 5
        
        # Verify we get the most recent messages
        assert context_messages[-1].content == "Context message 9"
        assert context_messages[0].content == "Context message 5"
    
    @pytest.mark.asyncio
    async def test_performance_with_high_message_volume(self, message_processor, db_manager):
        """Test performance with high volume of messages."""
        channel = "testchannel"
        message_count = 100
        
        start_time = datetime.now()
        
        # Process many messages quickly
        tasks = []
        for i in range(message_count):
            message_event = MessageEvent(
                message_id=f"perf-msg-{i}",
                channel=channel,
                user_id=f"user{i % 10}",  # Simulate 10 different users
                user_display_name=f"User{i % 10}",
                content=f"Performance test message {i}",
                timestamp=datetime.now() + timedelta(milliseconds=i),
                badges={}
            )
            task = message_processor.process_incoming_message(message_event)
            tasks.append(task)
        
        # Wait for all messages to be processed
        await asyncio.gather(*tasks)
        
        end_time = datetime.now()
        processing_time = (end_time - start_time).total_seconds()
        
        # Verify all messages were processed
        messages = await db_manager.get_recent_messages(channel, message_count + 10)
        assert len(messages) == message_count
        
        # Performance assertion - should process 100 messages in reasonable time
        assert processing_time < 10.0, f"Processing took too long: {processing_time}s"
        
        # Verify messages are in correct order (chronological)
        for i in range(len(messages) - 1):
            assert messages[i].timestamp <= messages[i + 1].timestamp