"""
Message generation triggers and timing logic.

This module handles when and how to trigger automatic message generation
with dual cooldown systems for spontaneous and response messages.
"""

import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from ..database.operations import ChannelConfigManager, DatabaseManager
from ..database.models import ChannelConfig

logger = logging.getLogger(__name__)


class RateLimitManager:
    """
    Manages dual cooldown systems for spontaneous and response rate limiting.
    
    This class implements two independent rate limiting systems:
    1. Spontaneous message cooldown (channel-level)
    2. Per-user response cooldown (user-specific)
    """
    
    def __init__(self, config_manager: ChannelConfigManager, db_manager: DatabaseManager):
        """
        Initialize the rate limit manager.
        
        Args:
            config_manager: Channel configuration manager
            db_manager: Database manager for user cooldown tracking
        """
        self.config_manager = config_manager
        self.db_manager = db_manager
        self.logger = logging.getLogger(__name__)
    
    async def should_generate_spontaneous_message(self, channel: str) -> bool:
        """
        Check if bot should generate a spontaneous message for a channel.
        
        This implements channel-level cooldown tracking for automatic message generation
        with configurable message count thresholds and time constraints.
        
        Args:
            channel: Channel name to check
            
        Returns:
            bool: True if should generate, False otherwise
        """
        try:
            config = await self.config_manager.get_config(channel)
            
            # Check message count threshold
            if config.message_count < config.message_threshold:
                self.logger.debug(
                    "Spontaneous generation blocked: insufficient message count",
                    extra={
                        "channel": channel,
                        "current_count": config.message_count,
                        "threshold": config.message_threshold
                    }
                )
                return False
            
            # Check spontaneous cooldown
            if config.last_spontaneous_message:
                time_since = datetime.now() - config.last_spontaneous_message
                if time_since.total_seconds() < config.spontaneous_cooldown:
                    remaining = config.spontaneous_cooldown - time_since.total_seconds()
                    self.logger.debug(
                        "Spontaneous generation blocked: cooldown active",
                        extra={
                            "channel": channel,
                            "cooldown_remaining_seconds": remaining,
                            "cooldown_duration": config.spontaneous_cooldown
                        }
                    )
                    return False
            
            # Check adequate context availability
            available_messages = await self.db_manager.count_recent_messages(channel)
            if available_messages < 10:
                self.logger.debug(
                    "Spontaneous generation blocked: insufficient context",
                    extra={
                        "channel": channel,
                        "available_messages": available_messages,
                        "minimum_required": 10
                    }
                )
                return False
            
            self.logger.info(
                "Spontaneous generation approved",
                extra={
                    "channel": channel,
                    "message_count": config.message_count,
                    "threshold": config.message_threshold,
                    "available_context": available_messages
                }
            )
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to check spontaneous generation for {channel}: {e}")
            return False
    
    async def can_respond_to_mention(self, channel: str, user_id: str) -> bool:
        """
        Check if bot can respond to a user's mention.
        
        This implements per-user response cooldown tracking that is independent
        of spontaneous message generation cooldowns.
        
        Args:
            channel: Channel name
            user_id: User ID who mentioned the bot
            
        Returns:
            bool: True if can respond, False otherwise
        """
        try:
            config = await self.config_manager.get_config(channel)
            
            # Get user's last response time
            last_response = await self._get_user_last_response(channel, user_id)
            
            if last_response:
                time_since = datetime.now() - last_response
                if time_since.total_seconds() < config.response_cooldown:
                    remaining = config.response_cooldown - time_since.total_seconds()
                    self.logger.info(
                        "User response rate limited",
                        extra={
                            "channel": channel,
                            "user_id": user_id,
                            "cooldown_remaining_seconds": remaining,
                            "cooldown_duration": config.response_cooldown
                        }
                    )
                    return False
            
            self.logger.debug(
                "User response approved",
                extra={
                    "channel": channel,
                    "user_id": user_id,
                    "response_cooldown": config.response_cooldown
                }
            )
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to check user response cooldown for {user_id} in {channel}: {e}")
            return False
    
    async def record_spontaneous_generation(self, channel: str) -> bool:
        """
        Record that a spontaneous message was generated.
        
        This resets the message counter and updates the last spontaneous message timestamp.
        
        Args:
            channel: Channel name
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            # Reset message count and update timestamp
            await self.config_manager.reset_message_count(channel)
            await self.config_manager.update_spontaneous_timestamp(channel)
            
            self.logger.info(
                "Spontaneous generation recorded",
                extra={
                    "channel": channel,
                    "timestamp": datetime.now().isoformat()
                }
            )
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to record spontaneous generation for {channel}: {e}")
            return False
    
    async def record_user_response(self, channel: str, user_id: str) -> bool:
        """
        Record that a response was sent to a user.
        
        This updates the user's response cooldown timestamp.
        
        Args:
            channel: Channel name
            user_id: User ID who was responded to
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            await self.config_manager.update_user_response_timestamp(channel, user_id)
            
            self.logger.info(
                "User response recorded",
                extra={
                    "channel": channel,
                    "user_id": user_id,
                    "timestamp": datetime.now().isoformat()
                }
            )
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to record user response for {user_id} in {channel}: {e}")
            return False
    
    async def increment_message_count(self, channel: str) -> int:
        """
        Increment the message count for a channel.
        
        This is called when a regular user message is processed and stored.
        
        Args:
            channel: Channel name
            
        Returns:
            int: New message count
        """
        try:
            new_count = await self.config_manager.increment_message_count(channel)
            
            self.logger.debug(
                "Message count incremented",
                extra={
                    "channel": channel,
                    "new_count": new_count
                }
            )
            return new_count
            
        except Exception as e:
            self.logger.error(f"Failed to increment message count for {channel}: {e}")
            return 0
    
    async def get_rate_limit_status(self, channel: str, user_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Get current rate limiting status for a channel and optionally a user.
        
        Args:
            channel: Channel name
            user_id: Optional user ID to check response cooldown
            
        Returns:
            Dictionary with rate limiting status information
        """
        try:
            config = await self.config_manager.get_config(channel)
            
            # Calculate spontaneous cooldown status
            spontaneous_ready = True
            spontaneous_remaining = 0
            
            if config.last_spontaneous_message:
                time_since = datetime.now() - config.last_spontaneous_message
                if time_since.total_seconds() < config.spontaneous_cooldown:
                    spontaneous_ready = False
                    spontaneous_remaining = config.spontaneous_cooldown - time_since.total_seconds()
            
            status = {
                "channel": channel,
                "message_count": config.message_count,
                "message_threshold": config.message_threshold,
                "spontaneous_cooldown": config.spontaneous_cooldown,
                "spontaneous_ready": spontaneous_ready,
                "spontaneous_remaining_seconds": max(0, spontaneous_remaining),
                "can_generate_spontaneous": await self.should_generate_spontaneous_message(channel)
            }
            
            # Add user-specific response cooldown status if user_id provided
            if user_id:
                response_ready = await self.can_respond_to_mention(channel, user_id)
                response_remaining = 0
                
                if not response_ready:
                    last_response = await self._get_user_last_response(channel, user_id)
                    if last_response:
                        time_since = datetime.now() - last_response
                        response_remaining = config.response_cooldown - time_since.total_seconds()
                
                status.update({
                    "user_id": user_id,
                    "response_cooldown": config.response_cooldown,
                    "response_ready": response_ready,
                    "response_remaining_seconds": max(0, response_remaining)
                })
            
            return status
            
        except Exception as e:
            self.logger.error(f"Failed to get rate limit status for {channel}: {e}")
            return {"error": str(e)}
    
    async def _get_user_last_response(self, channel: str, user_id: str) -> Optional[datetime]:
        """
        Get user's last response time from database.
        
        Args:
            channel: Channel name
            user_id: User ID
            
        Returns:
            Last response datetime or None if never responded
        """
        return await self.config_manager.get_user_last_response(channel, user_id)
    
    async def cleanup_old_user_cooldowns(self, days: int = 30) -> bool:
        """
        Clean up old user response cooldown records.
        
        Args:
            days: Number of days to retain cooldown records
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            cutoff_date = datetime.now() - timedelta(days=days)
            
            async with self.db_manager.get_connection() as conn:
                cursor = conn.cursor()
                
                if self.db_manager.db_type == 'sqlite':
                    cursor.execute("""
                        DELETE FROM user_response_cooldowns 
                        WHERE last_response_time < ?
                    """, (cutoff_date,))
                    conn.commit()
                    deleted_count = cursor.rowcount
                    
                elif self.db_manager.db_type == 'mysql':
                    cursor.execute("""
                        DELETE FROM user_response_cooldowns 
                        WHERE last_response_time < %s
                    """, (cutoff_date,))
                    deleted_count = cursor.rowcount
                
                self.logger.info(
                    "Cleaned up old user cooldown records",
                    extra={
                        "deleted_count": deleted_count,
                        "cutoff_days": days
                    }
                )
                return True
                
        except Exception as e:
            self.logger.error(f"Failed to cleanup old user cooldowns: {e}")
            return False


class MessageGenerationTrigger:
    """
    Handles message generation triggers with rate limiting integration.
    
    This class coordinates between rate limiting and actual message generation,
    ensuring that generation only occurs when rate limits allow.
    """
    
    def __init__(self, rate_limit_manager: RateLimitManager):
        """
        Initialize the message generation trigger.
        
        Args:
            rate_limit_manager: Rate limit manager instance
        """
        self.rate_limit_manager = rate_limit_manager
        self.logger = logging.getLogger(__name__)
    
    async def check_spontaneous_trigger(self, channel: str) -> bool:
        """
        Check if spontaneous message generation should be triggered.
        
        Args:
            channel: Channel name to check
            
        Returns:
            bool: True if should trigger generation, False otherwise
        """
        return await self.rate_limit_manager.should_generate_spontaneous_message(channel)
    
    async def check_mention_trigger(self, channel: str, user_id: str) -> bool:
        """
        Check if mention response generation should be triggered.
        
        Args:
            channel: Channel name
            user_id: User ID who mentioned the bot
            
        Returns:
            bool: True if should trigger response, False otherwise
        """
        return await self.rate_limit_manager.can_respond_to_mention(channel, user_id)
    
    async def record_generation(self, channel: str, generation_type: str, user_id: Optional[str] = None) -> bool:
        """
        Record that a message was generated.
        
        Args:
            channel: Channel name
            generation_type: 'spontaneous' or 'response'
            user_id: User ID for response messages
            
        Returns:
            bool: True if successful, False otherwise
        """
        if generation_type == 'spontaneous':
            return await self.rate_limit_manager.record_spontaneous_generation(channel)
        elif generation_type == 'response' and user_id:
            return await self.rate_limit_manager.record_user_response(channel, user_id)
        else:
            self.logger.error(f"Invalid generation type or missing user_id: {generation_type}, {user_id}")
            return False