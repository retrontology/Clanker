"""
Content filtering integration utilities.

This module provides integration points for content filtering
in the message processing pipeline.
"""

import logging
from typing import Optional
from .filters import ContentFilter


class FilteredMessageProcessor:
    """
    Message processor that integrates content filtering for both
    input processing and output validation.
    """
    
    def __init__(self, content_filter: ContentFilter):
        """
        Initialize the filtered message processor.
        
        Args:
            content_filter: ContentFilter instance to use for filtering
        """
        self.content_filter = content_filter
        self.logger = logging.getLogger(__name__)
    
    def process_incoming_message(self, message: str, user_id: str, channel: str) -> Optional[str]:
        """
        Process an incoming chat message with content filtering.
        
        This is the input filtering integration point that should be called
        before storing messages in the database.
        
        Args:
            message: The incoming chat message
            user_id: ID of the user who sent the message
            channel: Channel where the message was sent
            
        Returns:
            The filtered message if clean, None if blocked
        """
        if not message:
            return message
        
        # Apply input filtering
        filtered_message = self.content_filter.filter_input(message)
        
        if filtered_message is None:
            self.logger.info(
                "Incoming message blocked by content filter",
                extra={
                    "channel": channel,
                    "user_id": user_id,
                    "message_length": len(message),
                    "filter_type": "input"
                }
            )
            return None
        
        return filtered_message
    
    def validate_generated_message(self, message: str, channel: str, generation_type: str) -> Optional[str]:
        """
        Validate a bot-generated message with content filtering.
        
        This is the output filtering integration point that should be called
        before sending generated messages to chat.
        
        Args:
            message: The bot-generated message
            channel: Channel where the message will be sent
            generation_type: Type of generation ('spontaneous' or 'response')
            
        Returns:
            The validated message if clean, None if blocked
        """
        if not message:
            return message
        
        # Apply output filtering
        filtered_message = self.content_filter.filter_output(message)
        
        if filtered_message is None:
            self.logger.warning(
                "Generated message blocked by content filter",
                extra={
                    "channel": channel,
                    "generation_type": generation_type,
                    "message_length": len(message),
                    "filter_type": "output",
                    "blocked_content": message  # Log full content for debugging
                }
            )
            return None
        
        return filtered_message
    
    def is_message_safe_to_store(self, message: str) -> bool:
        """
        Check if a message is safe to store in the database.
        
        Args:
            message: Message to check
            
        Returns:
            True if safe to store, False otherwise
        """
        return self.content_filter.is_message_clean(message)
    
    def get_filter_stats(self) -> dict:
        """
        Get content filter statistics.
        
        Returns:
            Dictionary with filter statistics
        """
        return self.content_filter.get_stats()


def create_content_filter(blocked_words_file: str, enabled: bool = True) -> Optional[ContentFilter]:
    """
    Factory function to create a content filter instance.
    
    Args:
        blocked_words_file: Path to the blocked words configuration file
        enabled: Whether content filtering is enabled
        
    Returns:
        ContentFilter instance if enabled, None otherwise
    """
    if not enabled:
        logging.getLogger(__name__).warning("Content filtering is disabled")
        return None
    
    try:
        content_filter = ContentFilter(blocked_words_file)
        logging.getLogger(__name__).info(
            "Content filter initialized successfully",
            extra=content_filter.get_stats()
        )
        return content_filter
    except Exception as e:
        logging.getLogger(__name__).error(f"Failed to initialize content filter: {e}")
        # Return a basic filter that blocks everything as fail-safe
        return ContentFilter("")  # Empty file path will create a minimal filter


class NoOpFilter:
    """
    No-operation filter for when content filtering is disabled.
    
    This provides the same interface as ContentFilter but doesn't
    actually filter anything.
    """
    
    def filter_input(self, message: str) -> Optional[str]:
        """Pass-through input filtering."""
        return message
    
    def filter_output(self, message: str) -> Optional[str]:
        """Pass-through output filtering."""
        return message
    
    def is_message_clean(self, message: str) -> bool:
        """Always returns True."""
        return True
    
    def get_stats(self) -> dict:
        """Returns empty stats."""
        return {
            "blocked_words_count": 0,
            "blocked_patterns_count": 0,
            "config_file": "disabled"
        }
    
    def reload_blocked_words(self) -> None:
        """No-op reload."""
        pass