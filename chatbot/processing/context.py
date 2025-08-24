"""
Context window management for message generation.

This module handles building and managing context windows for both
spontaneous and response message generation with proper channel isolation.
"""

import logging
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta

from ..database.models import Message
from ..database.operations import DatabaseManager, ChannelConfigManager

logger = logging.getLogger(__name__)


class ContextWindowManager:
    """
    Manages context window building and retrieval for message generation.
    
    Provides configurable context limits with channel isolation and proper
    message ordering for both spontaneous and response generation scenarios.
    """
    
    def __init__(self, db_manager: DatabaseManager, config_manager: ChannelConfigManager):
        """
        Initialize ContextWindowManager.
        
        Args:
            db_manager: Database manager instance
            config_manager: Channel configuration manager
        """
        self.db_manager = db_manager
        self.config_manager = config_manager
        self._context_cache: Dict[str, List[Message]] = {}
        self._cache_timestamps: Dict[str, datetime] = {}
        self._cache_ttl_seconds = 30  # Cache context for 30 seconds
    
    async def build_context_window(self, 
                                 channel: str, 
                                 limit: Optional[int] = None,
                                 generation_type: str = 'spontaneous') -> List[Message]:
        """
        Build context window for message generation with configurable limits and channel isolation.
        
        Args:
            channel: Channel name
            limit: Maximum number of messages (uses channel config if None)
            generation_type: 'spontaneous' or 'response'
            
        Returns:
            List of Message objects in chronological order (oldest first)
        """
        try:
            # Use cached context if available and fresh
            cache_key = f"{channel}:{generation_type}"
            if self._is_cache_valid(cache_key):
                logger.debug(f"Using cached context for {channel} ({generation_type})")
                return self._context_cache[cache_key]
            
            # Get channel configuration for context limit
            if limit is None:
                config = await self.config_manager.get_config(channel)
                limit = config.context_limit
            
            # Adjust limit based on generation type
            effective_limit = self._adjust_limit_for_generation_type(limit, generation_type)
            
            # Retrieve messages from database
            messages = await self.db_manager.get_recent_messages(channel, effective_limit)
            
            # Filter and format messages for context
            context_messages = self._filter_messages_for_context(messages, generation_type)
            
            # Cache the result
            self._context_cache[cache_key] = context_messages
            self._cache_timestamps[cache_key] = datetime.now()
            
            logger.debug(
                "Context window built",
                extra={
                    "channel": channel,
                    "generation_type": generation_type,
                    "requested_limit": limit,
                    "effective_limit": effective_limit,
                    "messages_retrieved": len(messages),
                    "context_size": len(context_messages)
                }
            )
            
            return context_messages
            
        except Exception as e:
            logger.error(f"Error building context window for {channel}: {e}")
            return []
    
    def _adjust_limit_for_generation_type(self, base_limit: int, generation_type: str) -> int:
        """
        Adjust context limit based on generation type.
        
        Args:
            base_limit: Base context limit from configuration
            generation_type: 'spontaneous' or 'response'
            
        Returns:
            Adjusted limit
        """
        if generation_type == 'response':
            # For responses, use slightly fewer messages to leave room for user input
            return min(base_limit, max(15, int(base_limit * 0.75)))
        else:
            # For spontaneous messages, use the full limit
            return base_limit
    
    def _filter_messages_for_context(self, messages: List[Message], generation_type: str) -> List[Message]:
        """
        Filter and prepare messages for context window.
        
        Args:
            messages: Raw messages from database
            generation_type: 'spontaneous' or 'response'
            
        Returns:
            Filtered messages suitable for context
        """
        if not messages:
            return []
        
        # Basic filtering - remove very short messages that don't add context
        filtered_messages = []
        for msg in messages:
            # Skip very short messages (less than 3 characters)
            if len(msg.message_content.strip()) < 3:
                continue
            
            # Skip messages that are just emotes or single characters
            content = msg.message_content.strip()
            if len(content) == 1 or content.lower() in ['lol', 'lul', 'kek', 'omg', 'wtf']:
                continue
            
            filtered_messages.append(msg)
        
        # For spontaneous generation, prefer more diverse recent messages
        if generation_type == 'spontaneous':
            return self._select_diverse_messages(filtered_messages)
        else:
            # For responses, use recent messages as-is for immediate context
            return filtered_messages
    
    def _select_diverse_messages(self, messages: List[Message]) -> List[Message]:
        """
        Select diverse messages for spontaneous generation context.
        
        Args:
            messages: Filtered messages
            
        Returns:
            Diverse selection of messages
        """
        if len(messages) <= 20:
            return messages
        
        # Take most recent messages but try to include different users
        selected = []
        seen_users = set()
        
        # First pass: take recent messages from different users
        for msg in reversed(messages):  # Start from most recent
            if msg.user_id not in seen_users or len(selected) < 10:
                selected.append(msg)
                seen_users.add(msg.user_id)
                
                if len(selected) >= 20:
                    break
        
        # Return in chronological order
        return list(reversed(selected))
    
    def _is_cache_valid(self, cache_key: str) -> bool:
        """
        Check if cached context is still valid.
        
        Args:
            cache_key: Cache key to check
            
        Returns:
            True if cache is valid, False otherwise
        """
        if cache_key not in self._context_cache or cache_key not in self._cache_timestamps:
            return False
        
        cache_age = datetime.now() - self._cache_timestamps[cache_key]
        return cache_age.total_seconds() < self._cache_ttl_seconds
    
    async def invalidate_context_cache(self, channel: str) -> None:
        """
        Invalidate context cache for a channel.
        
        This should be called when messages are deleted or moderation events occur.
        
        Args:
            channel: Channel name
        """
        keys_to_remove = [key for key in self._context_cache.keys() if key.startswith(f"{channel}:")]
        
        for key in keys_to_remove:
            self._context_cache.pop(key, None)
            self._cache_timestamps.pop(key, None)
        
        logger.debug(f"Context cache invalidated for {channel}")
    
    async def get_context_info(self, channel: str) -> Dict[str, Any]:
        """
        Get information about context availability for a channel.
        
        Args:
            channel: Channel name
            
        Returns:
            Dictionary with context information
        """
        try:
            config = await self.config_manager.get_config(channel)
            
            # Get recent message count
            recent_count = await self.db_manager.count_recent_messages(channel, hours=24)
            
            # Get available context size
            available_messages = await self.db_manager.get_recent_messages(channel, config.context_limit)
            
            # Check if adequate context is available
            adequate_context = len(available_messages) >= 10
            
            return {
                "context_limit": config.context_limit,
                "recent_messages_24h": recent_count,
                "available_context_messages": len(available_messages),
                "adequate_context": adequate_context,
                "cache_status": {
                    "spontaneous_cached": f"{channel}:spontaneous" in self._context_cache,
                    "response_cached": f"{channel}:response" in self._context_cache
                }
            }
            
        except Exception as e:
            logger.error(f"Error getting context info for {channel}: {e}")
            return {"error": str(e)}
    
    async def preload_context(self, channels: List[str]) -> None:
        """
        Preload context for multiple channels.
        
        This can be called during startup or periodically to warm the cache.
        
        Args:
            channels: List of channel names to preload
        """
        try:
            for channel in channels:
                # Preload both spontaneous and response contexts
                await self.build_context_window(channel, generation_type='spontaneous')
                await self.build_context_window(channel, generation_type='response')
            
            logger.info(f"Context preloaded for {len(channels)} channels")
            
        except Exception as e:
            logger.error(f"Error preloading context: {e}")
    
    def cleanup_cache(self) -> None:
        """
        Clean up expired cache entries.
        
        This should be called periodically to prevent memory leaks.
        """
        try:
            now = datetime.now()
            expired_keys = []
            
            for key, timestamp in self._cache_timestamps.items():
                if (now - timestamp).total_seconds() > self._cache_ttl_seconds:
                    expired_keys.append(key)
            
            for key in expired_keys:
                self._context_cache.pop(key, None)
                self._cache_timestamps.pop(key, None)
            
            if expired_keys:
                logger.debug(f"Cleaned up {len(expired_keys)} expired cache entries")
                
        except Exception as e:
            logger.error(f"Error cleaning up context cache: {e}")
    
    def get_cache_stats(self) -> Dict[str, Any]:
        """
        Get cache statistics.
        
        Returns:
            Dictionary with cache statistics
        """
        return {
            "cached_contexts": len(self._context_cache),
            "cache_ttl_seconds": self._cache_ttl_seconds,
            "cache_keys": list(self._context_cache.keys())
        }