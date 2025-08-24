#!/usr/bin/env python3
"""
Example demonstrating how to integrate logging and metrics into chatbot components.

This example shows various patterns for adding structured logging and performance
metrics to existing chatbot components.
"""

import asyncio
import sys
import time
from pathlib import Path
from typing import List, Optional

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from chatbot.logging import (
    LoggingMixin,
    log_async_operation,
    track_metrics,
    PerformanceMonitor,
    setup_component_logging,
    get_logger,
    MetricsManager,
    log_generation_event,
    log_filter_event,
    log_rate_limit_event
)
from chatbot.database.operations import DatabaseManager


# Example 1: Using LoggingMixin
class MessageProcessor(LoggingMixin):
    """Example message processor with integrated logging."""
    
    def __init__(self, metrics_manager: MetricsManager):
        super().__init__()
        self.setup_logging("message_processor")
        self.metrics = metrics_manager
    
    async def process_message(self, channel: str, user: str, content: str) -> bool:
        """Process a chat message with logging."""
        self.log_operation(
            "Processing message",
            channel=channel,
            user=user,
            message_length=len(content)
        )
        
        try:
            # Simulate processing
            await asyncio.sleep(0.1)
            
            # Log success
            self.logger.info(
                "Message processed successfully",
                channel=channel,
                user=user,
                processing_time_ms=100
            )
            
            return True
            
        except Exception as e:
            self.log_error("Processing message", e, channel=channel, user=user)
            return False


# Example 2: Using decorators
class OllamaClient:
    """Example Ollama client with decorator-based logging and metrics."""
    
    def __init__(self, metrics_manager: MetricsManager):
        self.logger = get_logger("ollama_client")
        self.metrics = metrics_manager
    
    @log_async_operation("ollama_request", include_timing=True)
    async def generate_message(self, channel: str, prompt: str) -> str:
        """Generate a message using Ollama with automatic logging and metrics."""
        start_time = time.time()
        
        try:
            # Simulate Ollama API call
            await asyncio.sleep(0.5)  # Simulate network delay
            
            generated_message = f"Generated response for: {prompt[:50]}..."
            
            # Record success metrics
            duration_ms = (time.time() - start_time) * 1000
            await self.metrics.record_response_time(channel, duration_ms)
            await self.metrics.record_success(channel, "ollama_generation")
            
            return generated_message
            
        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            await self.metrics.record_response_time(channel, duration_ms)
            await self.metrics.record_error(channel, "api_error", "ollama_generation")
            raise


# Example 3: Using class decorator
@setup_component_logging("content_filter")
class ContentFilter:
    """Example content filter with automatic logging setup."""
    
    def __init__(self, metrics_manager: MetricsManager):
        # self.logger is automatically available due to decorator
        self.metrics = metrics_manager
        self.blocked_words = ["spam", "inappropriate"]
    
    async def filter_content(self, channel: str, content: str) -> Optional[str]:
        """Filter content with integrated logging and metrics."""
        self.logger.debug("Filtering content", channel=channel, content_length=len(content))
        
        # Check for blocked words
        content_lower = content.lower()
        for word in self.blocked_words:
            if word in content_lower:
                # Log filter block
                await log_filter_event(
                    self.logger,
                    self.metrics,
                    channel=channel,
                    filter_type="input",
                    blocked=True,
                    content_sample=content,
                    blocked_word=word
                )
                return None
        
        # Content passed filter
        await log_filter_event(
            self.logger,
            self.metrics,
            channel=channel,
            filter_type="input",
            blocked=False
        )
        
        return content


# Example 4: Using PerformanceMonitor context manager
class DatabaseService:
    """Example database service with performance monitoring."""
    
    def __init__(self, db_manager: DatabaseManager, metrics_manager: MetricsManager):
        self.db = db_manager
        self.metrics = metrics_manager
        self.logger = get_logger("database_service")
    
    async def get_recent_messages(self, channel: str, limit: int = 100) -> List[str]:
        """Get recent messages with performance monitoring."""
        async with PerformanceMonitor(
            self.metrics,
            "database_query",
            channel,
            "database_operation"
        ):
            # Simulate database query
            await asyncio.sleep(0.2)
            
            # Return mock data
            return [f"Message {i} from {channel}" for i in range(limit)]


# Example 5: Comprehensive component with all patterns
class ChatbotCoordinator(LoggingMixin):
    """Main coordinator showing comprehensive logging integration."""
    
    def __init__(self, db_manager: DatabaseManager, metrics_manager: MetricsManager):
        super().__init__()
        self.setup_logging("chatbot_coordinator")
        
        self.db_service = DatabaseService(db_manager, metrics_manager)
        self.ollama_client = OllamaClient(metrics_manager)
        self.content_filter = ContentFilter(metrics_manager)
        self.message_processor = MessageProcessor(metrics_manager)
        self.metrics = metrics_manager
    
    async def handle_message(self, channel: str, user: str, content: str) -> Optional[str]:
        """Handle incoming message with comprehensive logging."""
        self.log_operation(
            "Handling incoming message",
            channel=channel,
            user=user,
            message_length=len(content)
        )
        
        try:
            # Filter content
            filtered_content = await self.content_filter.filter_content(channel, content)
            if not filtered_content:
                self.log_warning(
                    "Message blocked by filter",
                    "Content filter blocked message",
                    channel=channel,
                    user=user
                )
                return None
            
            # Process message
            processed = await self.message_processor.process_message(channel, user, filtered_content)
            if not processed:
                return None
            
            # Check if we should generate a response
            if await self._should_generate_response(channel):
                return await self._generate_response(channel, filtered_content)
            
            return None
            
        except Exception as e:
            self.log_error("Handling message", e, channel=channel, user=user)
            return None
    
    async def _should_generate_response(self, channel: str) -> bool:
        """Check if bot should generate a response."""
        # Simulate rate limiting check
        await asyncio.sleep(0.05)
        
        # Simulate rate limit hit 30% of the time
        import random
        if random.random() < 0.3:
            await log_rate_limit_event(
                self.logger,
                self.metrics,
                channel=channel,
                limit_type="spontaneous",
                remaining_seconds=120.0
            )
            return False
        
        return True
    
    async def _generate_response(self, channel: str, context: str) -> str:
        """Generate response with comprehensive logging."""
        start_time = time.time()
        
        try:
            # Get context from database
            recent_messages = await self.db_service.get_recent_messages(channel, 50)
            
            # Generate response
            response = await self.ollama_client.generate_message(channel, context)
            
            # Filter output
            filtered_response = await self.content_filter.filter_content(channel, response)
            if not filtered_response:
                self.log_warning(
                    "Generated response blocked by filter",
                    "Output filter blocked generated content",
                    channel=channel
                )
                return None
            
            # Log successful generation
            duration_ms = (time.time() - start_time) * 1000
            await log_generation_event(
                self.logger,
                self.metrics,
                channel=channel,
                generation_type="response",
                success=True,
                duration_ms=duration_ms,
                model_used="llama3.1",
                context_size=len(recent_messages)
            )
            
            return filtered_response
            
        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            await log_generation_event(
                self.logger,
                self.metrics,
                channel=channel,
                generation_type="response",
                success=False,
                duration_ms=duration_ms,
                model_used="llama3.1",
                error=str(e)
            )
            raise


async def main():
    """Demonstrate the logging integration."""
    print("Starting logging integration example...\n")
    
    # Set up database and metrics (using temporary database)
    import tempfile
    import os
    
    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as tmp_file:
        db_path = tmp_file.name
    
    try:
        # Initialize components
        db_manager = DatabaseManager(db_type="sqlite", database_url=db_path)
        await db_manager.initialize()
        
        metrics_manager = MetricsManager(db_manager)
        
        # Create coordinator
        coordinator = ChatbotCoordinator(db_manager, metrics_manager)
        
        # Simulate message handling
        test_messages = [
            ("testchannel", "user1", "Hello everyone!"),
            ("testchannel", "user2", "How's it going?"),
            ("testchannel", "user3", "This is spam content"),  # Will be filtered
            ("testchannel", "user4", "What do you think about the game?"),
        ]
        
        for channel, user, content in test_messages:
            print(f"Processing: [{channel}] {user}: {content}")
            response = await coordinator.handle_message(channel, user, content)
            if response:
                print(f"Bot response: {response}")
            print()
        
        # Show metrics
        print("=== Performance Statistics ===")
        stats = await metrics_manager.get_performance_stats("testchannel", hours=1)
        print(f"Channel stats: {stats}")
        
        session_stats = await metrics_manager.get_session_stats()
        print(f"Session stats: {session_stats}")
        
        # Cleanup
        await metrics_manager.shutdown()
        
    finally:
        # Clean up temporary database
        if os.path.exists(db_path):
            os.unlink(db_path)
    
    print("\nLogging integration example completed!")


if __name__ == "__main__":
    asyncio.run(main())