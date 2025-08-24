"""
Performance tests for database operations and context window management.

Tests system performance under various load conditions and validates
that operations complete within acceptable time limits.
"""

import pytest
import asyncio
import time
from datetime import datetime, timedelta
from typing import List
import statistics

from chatbot.database.operations import DatabaseManager, ChannelConfigManager
from chatbot.database.models import MessageEvent, Message
from chatbot.ollama.client import OllamaClient
from chatbot.processing.filters import ContentFilter
from tests.conftest import create_test_message


class TestDatabasePerformance:
    """Performance tests for database operations."""
    
    @pytest.mark.asyncio
    async def test_message_storage_performance(self, db_manager):
        """Test performance of message storage operations."""
        channel = "perftest"
        message_count = 1000
        
        # Generate test messages
        messages = []
        for i in range(message_count):
            message = MessageEvent(
                message_id=f"perf-msg-{i}",
                channel=channel,
                user_id=f"user{i % 100}",  # 100 different users
                user_display_name=f"User{i % 100}",
                content=f"Performance test message {i} with some content to make it realistic",
                timestamp=datetime.now() + timedelta(milliseconds=i),
                badges={"subscriber": "1"} if i % 3 == 0 else {}
            )
            messages.append(message)
        
        # Measure storage performance
        start_time = time.time()
        
        # Store messages sequentially
        for message in messages:
            await db_manager.store_message(message)
        
        end_time = time.time()
        total_time = end_time - start_time
        
        # Performance assertions
        assert total_time < 30.0, f"Storing {message_count} messages took too long: {total_time:.2f}s"
        
        messages_per_second = message_count / total_time
        assert messages_per_second > 30, f"Storage rate too slow: {messages_per_second:.2f} msg/s"
        
        # Verify all messages were stored
        stored_messages = await db_manager.get_recent_messages(channel, message_count + 100)
        assert len(stored_messages) == message_count
    
    @pytest.mark.asyncio
    async def test_concurrent_message_storage_performance(self, db_manager):
        """Test performance of concurrent message storage."""
        channel = "concurrency_test"
        message_count = 500
        batch_size = 50
        
        # Generate test messages
        messages = []
        for i in range(message_count):
            message = MessageEvent(
                message_id=f"concurrent-msg-{i}",
                channel=channel,
                user_id=f"user{i % 50}",
                user_display_name=f"User{i % 50}",
                content=f"Concurrent test message {i}",
                timestamp=datetime.now() + timedelta(milliseconds=i),
                badges={}
            )
            messages.append(message)
        
        # Measure concurrent storage performance
        start_time = time.time()
        
        # Store messages in concurrent batches
        for i in range(0, message_count, batch_size):
            batch = messages[i:i + batch_size]
            tasks = [db_manager.store_message(msg) for msg in batch]
            await asyncio.gather(*tasks)
        
        end_time = time.time()
        total_time = end_time - start_time
        
        # Performance assertions
        assert total_time < 20.0, f"Concurrent storage took too long: {total_time:.2f}s"
        
        messages_per_second = message_count / total_time
        assert messages_per_second > 25, f"Concurrent storage rate too slow: {messages_per_second:.2f} msg/s"
        
        # Verify all messages were stored
        stored_messages = await db_manager.get_recent_messages(channel, message_count + 100)
        assert len(stored_messages) == message_count
    
    @pytest.mark.asyncio
    async def test_message_retrieval_performance(self, db_manager):
        """Test performance of message retrieval operations."""
        channel = "retrieval_test"
        total_messages = 5000
        
        # Store a large number of messages
        for i in range(total_messages):
            message = MessageEvent(
                message_id=f"retrieval-msg-{i}",
                channel=channel,
                user_id=f"user{i % 200}",
                user_display_name=f"User{i % 200}",
                content=f"Retrieval test message {i}",
                timestamp=datetime.now() + timedelta(seconds=i),
                badges={}
            )
            await db_manager.store_message(message)
        
        # Test retrieval performance with different limits
        retrieval_tests = [10, 50, 100, 200, 500, 1000]
        
        for limit in retrieval_tests:
            start_time = time.time()
            
            # Perform multiple retrievals to get average performance
            for _ in range(10):
                messages = await db_manager.get_recent_messages(channel, limit)
                assert len(messages) == limit
            
            end_time = time.time()
            avg_time = (end_time - start_time) / 10
            
            # Performance assertions - should retrieve messages quickly
            max_time = 0.1 + (limit * 0.0001)  # Scale with message count
            assert avg_time < max_time, f"Retrieving {limit} messages took too long: {avg_time:.3f}s"
    
    @pytest.mark.asyncio
    async def test_database_cleanup_performance(self, db_manager):
        """Test performance of database cleanup operations."""
        channel = "cleanup_test"
        message_count = 2000
        
        # Store messages with different timestamps
        old_time = datetime.now() - timedelta(days=10)
        recent_time = datetime.now() - timedelta(hours=1)
        
        # Store old messages
        for i in range(message_count // 2):
            message = MessageEvent(
                message_id=f"old-msg-{i}",
                channel=channel,
                user_id=f"user{i}",
                user_display_name=f"User{i}",
                content=f"Old message {i}",
                timestamp=old_time + timedelta(minutes=i),
                badges={}
            )
            await db_manager.store_message(message)
        
        # Store recent messages
        for i in range(message_count // 2):
            message = MessageEvent(
                message_id=f"recent-msg-{i}",
                channel=channel,
                user_id=f"user{i}",
                user_display_name=f"User{i}",
                content=f"Recent message {i}",
                timestamp=recent_time + timedelta(minutes=i),
                badges={}
            )
            await db_manager.store_message(message)
        
        # Measure cleanup performance
        start_time = time.time()
        
        result = await db_manager.cleanup_old_messages(channel, retention_days=7)
        
        end_time = time.time()
        cleanup_time = end_time - start_time
        
        # Performance assertions
        assert result is True
        assert cleanup_time < 5.0, f"Cleanup took too long: {cleanup_time:.2f}s"
        
        # Verify cleanup worked correctly
        remaining_messages = await db_manager.get_recent_messages(channel, message_count)
        assert len(remaining_messages) == message_count // 2  # Only recent messages should remain
    
    @pytest.mark.asyncio
    async def test_channel_isolation_performance(self, db_manager):
        """Test performance with multiple channels."""
        channel_count = 10
        messages_per_channel = 200
        
        # Store messages across multiple channels
        start_time = time.time()
        
        for channel_idx in range(channel_count):
            channel = f"channel_{channel_idx}"
            
            for msg_idx in range(messages_per_channel):
                message = MessageEvent(
                    message_id=f"ch{channel_idx}-msg-{msg_idx}",
                    channel=channel,
                    user_id=f"user{msg_idx}",
                    user_display_name=f"User{msg_idx}",
                    content=f"Message {msg_idx} in {channel}",
                    timestamp=datetime.now() + timedelta(seconds=msg_idx),
                    badges={}
                )
                await db_manager.store_message(message)
        
        storage_time = time.time() - start_time
        
        # Test retrieval performance across channels
        retrieval_start = time.time()
        
        for channel_idx in range(channel_count):
            channel = f"channel_{channel_idx}"
            messages = await db_manager.get_recent_messages(channel, 50)
            assert len(messages) == 50
            
            # Verify channel isolation
            for msg in messages:
                assert msg.channel == channel
        
        retrieval_time = time.time() - retrieval_start
        
        # Performance assertions
        total_messages = channel_count * messages_per_channel
        storage_rate = total_messages / storage_time
        assert storage_rate > 20, f"Multi-channel storage too slow: {storage_rate:.2f} msg/s"
        
        retrieval_rate = (channel_count * 50) / retrieval_time
        assert retrieval_rate > 100, f"Multi-channel retrieval too slow: {retrieval_rate:.2f} msg/s"
    
    @pytest.mark.asyncio
    async def test_user_message_deletion_performance(self, db_manager):
        """Test performance of user message deletion operations."""
        channel = "deletion_test"
        users_count = 50
        messages_per_user = 40
        
        # Store messages from multiple users
        for user_idx in range(users_count):
            user_id = f"user_{user_idx}"
            
            for msg_idx in range(messages_per_user):
                message = MessageEvent(
                    message_id=f"user{user_idx}-msg-{msg_idx}",
                    channel=channel,
                    user_id=user_id,
                    user_display_name=f"User{user_idx}",
                    content=f"Message {msg_idx} from {user_id}",
                    timestamp=datetime.now() + timedelta(seconds=msg_idx),
                    badges={}
                )
                await db_manager.store_message(message)
        
        # Test deletion performance
        users_to_delete = users_count // 2
        deletion_times = []
        
        for user_idx in range(users_to_delete):
            user_id = f"user_{user_idx}"
            
            start_time = time.time()
            result = await db_manager.delete_user_messages(channel, user_id)
            end_time = time.time()
            
            assert result is True
            deletion_times.append(end_time - start_time)
        
        # Performance assertions
        avg_deletion_time = statistics.mean(deletion_times)
        max_deletion_time = max(deletion_times)
        
        assert avg_deletion_time < 0.1, f"Average user deletion too slow: {avg_deletion_time:.3f}s"
        assert max_deletion_time < 0.5, f"Max user deletion too slow: {max_deletion_time:.3f}s"
        
        # Verify deletions worked correctly
        remaining_messages = await db_manager.get_recent_messages(channel, 10000)
        remaining_users = set(msg.user_id for msg in remaining_messages)
        
        # Should only have messages from users that weren't deleted
        expected_remaining = users_count - users_to_delete
        assert len(remaining_users) == expected_remaining


class TestContextWindowPerformance:
    """Performance tests for context window management."""
    
    @pytest.mark.asyncio
    async def test_context_window_building_performance(self, db_manager):
        """Test performance of context window building."""
        channel = "context_test"
        total_messages = 10000
        
        # Store a large number of messages
        for i in range(total_messages):
            message = MessageEvent(
                message_id=f"context-msg-{i}",
                channel=channel,
                user_id=f"user{i % 100}",
                user_display_name=f"User{i % 100}",
                content=f"Context message {i} with realistic content length for testing",
                timestamp=datetime.now() + timedelta(seconds=i),
                badges={}
            )
            await db_manager.store_message(message)
        
        # Test context window building with different sizes
        context_sizes = [50, 100, 200, 500, 1000]
        
        for context_size in context_sizes:
            retrieval_times = []
            
            # Perform multiple retrievals to get average performance
            for _ in range(20):
                start_time = time.time()
                messages = await db_manager.get_recent_messages(channel, context_size)
                end_time = time.time()
                
                assert len(messages) == context_size
                retrieval_times.append(end_time - start_time)
            
            avg_time = statistics.mean(retrieval_times)
            max_time = max(retrieval_times)
            
            # Performance assertions - should scale reasonably with context size
            max_allowed_time = 0.05 + (context_size * 0.0001)
            assert avg_time < max_allowed_time, f"Context size {context_size} too slow: {avg_time:.3f}s"
            assert max_time < max_allowed_time * 2, f"Context size {context_size} max time too slow: {max_time:.3f}s"
    
    @pytest.mark.asyncio
    async def test_context_window_memory_efficiency(self, db_manager):
        """Test memory efficiency of context window operations."""
        channel = "memory_test"
        message_count = 5000
        
        # Store messages
        for i in range(message_count):
            message = MessageEvent(
                message_id=f"memory-msg-{i}",
                channel=channel,
                user_id=f"user{i % 50}",
                user_display_name=f"User{i % 50}",
                content=f"Memory test message {i} " * 10,  # Longer content
                timestamp=datetime.now() + timedelta(seconds=i),
                badges={}
            )
            await db_manager.store_message(message)
        
        # Test that we can handle multiple concurrent context retrievals
        # without excessive memory usage
        concurrent_retrievals = 20
        context_size = 200
        
        start_time = time.time()
        
        tasks = []
        for _ in range(concurrent_retrievals):
            task = db_manager.get_recent_messages(channel, context_size)
            tasks.append(task)
        
        results = await asyncio.gather(*tasks)
        
        end_time = time.time()
        total_time = end_time - start_time
        
        # Performance assertions
        assert total_time < 2.0, f"Concurrent context retrieval too slow: {total_time:.2f}s"
        
        # Verify all results are correct
        for messages in results:
            assert len(messages) == context_size
            # Verify messages are in chronological order
            for i in range(len(messages) - 1):
                assert messages[i].timestamp <= messages[i + 1].timestamp
    
    @pytest.mark.asyncio
    async def test_large_context_window_performance(self, db_manager):
        """Test performance with very large context windows."""
        channel = "large_context_test"
        message_count = 20000
        
        # Store a very large number of messages
        batch_size = 100
        for batch_start in range(0, message_count, batch_size):
            batch_tasks = []
            for i in range(batch_start, min(batch_start + batch_size, message_count)):
                message = MessageEvent(
                    message_id=f"large-msg-{i}",
                    channel=channel,
                    user_id=f"user{i % 200}",
                    user_display_name=f"User{i % 200}",
                    content=f"Large context test message {i}",
                    timestamp=datetime.now() + timedelta(seconds=i),
                    badges={}
                )
                batch_tasks.append(db_manager.store_message(message))
            
            await asyncio.gather(*batch_tasks)
        
        # Test retrieval of very large context windows
        large_context_sizes = [1000, 2000, 5000]
        
        for context_size in large_context_sizes:
            start_time = time.time()
            messages = await db_manager.get_recent_messages(channel, context_size)
            end_time = time.time()
            
            retrieval_time = end_time - start_time
            
            # Performance assertions
            max_allowed_time = 0.5 + (context_size * 0.0002)  # Scale with size
            assert retrieval_time < max_allowed_time, f"Large context {context_size} too slow: {retrieval_time:.2f}s"
            
            assert len(messages) == context_size
            
            # Verify ordering is correct
            for i in range(len(messages) - 1):
                assert messages[i].timestamp <= messages[i + 1].timestamp


class TestContentFilterPerformance:
    """Performance tests for content filtering operations."""
    
    def test_content_filter_performance(self, temp_blocked_words_file):
        """Test performance of content filtering operations."""
        content_filter = ContentFilter(temp_blocked_words_file)
        
        # Generate test messages of varying lengths
        test_messages = [
            "Short message",
            "This is a medium length message with some content",
            "This is a much longer message that contains a lot more text and should test the performance of the content filter with longer inputs that might be more realistic in actual chat scenarios",
            "SPAM " * 100,  # Very long message
            "Mixed case Message With Various CAPS and lowercase",
            "Message with numbers 123 and symbols !@#$%^&*()",
            "Unicode message with émojis 🎮 and spëcial chars",
        ]
        
        # Test input filtering performance
        start_time = time.time()
        
        for _ in range(1000):
            for message in test_messages:
                result = content_filter.filter_input(message)
                # Result should be either the message or None
                assert result is None or isinstance(result, str)
        
        end_time = time.time()
        input_filter_time = end_time - start_time
        
        # Test output filtering performance
        start_time = time.time()
        
        for _ in range(1000):
            for message in test_messages:
                result = content_filter.filter_output(message)
                assert result is None or isinstance(result, str)
        
        end_time = time.time()
        output_filter_time = end_time - start_time
        
        # Performance assertions
        messages_per_iteration = len(test_messages)
        total_input_operations = 1000 * messages_per_iteration
        total_output_operations = 1000 * messages_per_iteration
        
        input_ops_per_second = total_input_operations / input_filter_time
        output_ops_per_second = total_output_operations / output_filter_time
        
        assert input_ops_per_second > 1000, f"Input filtering too slow: {input_ops_per_second:.0f} ops/s"
        assert output_ops_per_second > 1000, f"Output filtering too slow: {output_ops_per_second:.0f} ops/s"
    
    def test_blocked_words_loading_performance(self):
        """Test performance of blocked words loading."""
        # Create a large blocked words file content
        large_blocked_words = []
        for i in range(1000):
            large_blocked_words.append(f"blockedword{i}")
            large_blocked_words.append(f"blocked phrase {i}")
        
        blocked_words_content = "\n".join([
            "# Large blocked words file for performance testing"
        ] + large_blocked_words)
        
        # Create temporary file
        import tempfile
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            f.write(blocked_words_content)
            temp_file = f.name
        
        try:
            # Test loading performance
            start_time = time.time()
            content_filter = ContentFilter(temp_file)
            end_time = time.time()
            
            loading_time = end_time - start_time
            
            # Performance assertions
            assert loading_time < 2.0, f"Blocked words loading too slow: {loading_time:.2f}s"
            assert len(content_filter.blocked_words) > 0
            assert len(content_filter.blocked_patterns) > 0
            
        finally:
            # Cleanup
            import os
            os.unlink(temp_file)