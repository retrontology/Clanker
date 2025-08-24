"""
Message event handlers for IRC events.

This module provides handler classes for processing incoming messages,
moderation events, and other IRC events with proper logging and error handling.
"""

import logging
from typing import Dict, Any, Callable, Optional
from datetime import datetime

from ..database.models import MessageEvent
from ..database.operations import DatabaseManager, ChannelConfigManager

logger = logging.getLogger(__name__)


class ModerationEventHandler:
    """
    Handler for moderation events (CLEARMSG, CLEARCHAT).
    
    Provides logging and context window management for moderation actions.
    """
    
    def __init__(self, db_manager: DatabaseManager, config_manager: ChannelConfigManager):
        """
        Initialize ModerationEventHandler.
        
        Args:
            db_manager: Database manager instance
            config_manager: Channel configuration manager
        """
        self.db_manager = db_manager
        self.config_manager = config_manager
    
    async def handle_moderation_event(self, event: Dict[str, Any]) -> None:
        """
        Handle moderation events with logging and context updates.
        
        Args:
            event: Moderation event dictionary with type and details
        """
        try:
            event_type = event.get('type')
            channel = event.get('channel')
            
            if event_type == 'clearmsg':
                await self._handle_single_message_deletion(event)
            elif event_type == 'clearchat_user':
                await self._handle_user_messages_deletion(event)
            elif event_type == 'clearchat_all':
                await self._handle_full_chat_clear(event)
            else:
                logger.warning(f"Unknown moderation event type: {event_type}")
                
        except Exception as e:
            logger.error(f"Error handling moderation event: {e}")
    
    async def _handle_single_message_deletion(self, event: Dict[str, Any]) -> None:
        """Handle single message deletion (CLEARMSG)."""
        channel = event.get('channel')
        message_id = event.get('message_id')
        
        logger.info(
            "Single message deleted by moderation",
            extra={
                "event_type": "clearmsg",
                "channel": channel,
                "message_id": message_id,
                "timestamp": datetime.now().isoformat()
            }
        )
        
        # Context window is automatically updated by database deletion
        # No additional action needed
    
    async def _handle_user_messages_deletion(self, event: Dict[str, Any]) -> None:
        """Handle user timeout/ban (CLEARCHAT user)."""
        channel = event.get('channel')
        user_id = event.get('user_id')
        
        logger.info(
            "User messages deleted by moderation (timeout/ban)",
            extra={
                "event_type": "clearchat_user",
                "channel": channel,
                "user_id": user_id,
                "timestamp": datetime.now().isoformat()
            }
        )
        
        # Context window is automatically updated by database deletion
        # Could potentially trigger context window rebuild if needed
    
    async def _handle_full_chat_clear(self, event: Dict[str, Any]) -> None:
        """Handle full chat clear (CLEARCHAT all)."""
        channel = event.get('channel')
        
        logger.info(
            "Full chat cleared by moderation",
            extra={
                "event_type": "clearchat_all",
                "channel": channel,
                "timestamp": datetime.now().isoformat()
            }
        )
        
        # Reset message count since all messages are gone
        await self.config_manager.reset_message_count(channel)


class MessageEventHandler:
    """
    Handler for regular message events.
    
    Provides processing pipeline for incoming messages with mention detection
    and trigger logic for message generation.
    """
    
    def __init__(self, 
                 db_manager: DatabaseManager, 
                 config_manager: ChannelConfigManager,
                 generation_trigger: Optional[Callable] = None):
        """
        Initialize MessageEventHandler.
        
        Args:
            db_manager: Database manager instance
            config_manager: Channel configuration manager
            generation_trigger: Optional callback for triggering message generation
        """
        self.db_manager = db_manager
        self.config_manager = config_manager
        self.generation_trigger = generation_trigger
    
    async def handle_message_event(self, message_event: MessageEvent) -> None:
        """
        Handle incoming message events with generation triggers.
        
        Args:
            message_event: MessageEvent instance
        """
        try:
            channel = message_event.channel
            
            # Log the message event
            logger.debug(
                "Processing message event",
                extra={
                    "channel": channel,
                    "user": message_event.user_display_name,
                    "is_mention": getattr(message_event, 'is_mention', False),
                    "content_length": len(message_event.content)
                }
            )
            
            # Handle mentions separately
            if getattr(message_event, 'is_mention', False):
                await self._handle_mention_message(message_event)
            else:
                await self._handle_regular_message(message_event)
                
        except Exception as e:
            logger.error(f"Error handling message event: {e}")
    
    async def _handle_mention_message(self, message_event: MessageEvent) -> None:
        """Handle messages that mention the bot."""
        channel = message_event.channel
        user_id = message_event.user_id
        
        # Check if we can respond to this user (rate limiting)
        can_respond = await self.config_manager.can_respond_to_user(channel, user_id)
        
        if can_respond and self.generation_trigger:
            # Trigger response generation
            mention_content = getattr(message_event, 'mention_content', message_event.content)
            
            logger.info(
                "Triggering mention response",
                extra={
                    "channel": channel,
                    "user": message_event.user_display_name,
                    "user_id": user_id,
                    "mention_content": mention_content
                }
            )
            
            try:
                await self.generation_trigger(
                    channel=channel,
                    is_mention=True,
                    user_input=mention_content,
                    user_name=message_event.user_display_name,
                    user_id=user_id
                )
            except Exception as e:
                logger.error(f"Error triggering mention response: {e}")
        else:
            if not can_respond:
                logger.debug(
                    "User mention rate limited",
                    extra={
                        "channel": channel,
                        "user_id": user_id,
                        "user": message_event.user_display_name
                    }
                )
    
    async def _handle_regular_message(self, message_event: MessageEvent) -> None:
        """Handle regular (non-mention) messages."""
        channel = message_event.channel
        
        # Check if we should generate a spontaneous message
        can_generate = await self.config_manager.can_generate_spontaneous(channel)
        
        if can_generate and self.generation_trigger:
            logger.info(
                "Triggering spontaneous message generation",
                extra={
                    "channel": channel,
                    "trigger_reason": "threshold_reached"
                }
            )
            
            try:
                await self.generation_trigger(
                    channel=channel,
                    is_mention=False
                )
            except Exception as e:
                logger.error(f"Error triggering spontaneous generation: {e}")


class IRCEventCoordinator:
    """
    Coordinates IRC events between the client and various handlers.
    
    Provides a centralized way to manage event routing and handler registration.
    """
    
    def __init__(self, 
                 db_manager: DatabaseManager, 
                 config_manager: ChannelConfigManager):
        """
        Initialize IRCEventCoordinator.
        
        Args:
            db_manager: Database manager instance
            config_manager: Channel configuration manager
        """
        self.db_manager = db_manager
        self.config_manager = config_manager
        
        # Initialize handlers
        self.moderation_handler = ModerationEventHandler(db_manager, config_manager)
        self.message_handler = MessageEventHandler(db_manager, config_manager)
        
        # Generation trigger callback
        self._generation_trigger: Optional[Callable] = None
    
    def set_generation_trigger(self, trigger_callback: Callable) -> None:
        """
        Set the generation trigger callback.
        
        Args:
            trigger_callback: Async function to call for message generation
        """
        self._generation_trigger = trigger_callback
        self.message_handler.generation_trigger = trigger_callback
    
    async def handle_message(self, message_event: MessageEvent) -> None:
        """
        Handle incoming message events.
        
        Args:
            message_event: MessageEvent instance
        """
        await self.message_handler.handle_message_event(message_event)
    
    async def handle_moderation(self, moderation_event: Dict[str, Any]) -> None:
        """
        Handle moderation events.
        
        Args:
            moderation_event: Moderation event dictionary
        """
        await self.moderation_handler.handle_moderation_event(moderation_event)
    
    def get_message_handler(self) -> Callable:
        """Get the message handler function for IRC client."""
        return self.handle_message
    
    def get_moderation_handler(self) -> Callable:
        """Get the moderation handler function for IRC client."""
        return self.handle_moderation