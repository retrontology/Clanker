"""
Message processing coordinator.

This module implements the main MessageProcessor that coordinates message filtering,
generation triggers, and AI interaction for the Twitch chatbot.
"""

import logging
from typing import Optional, Dict, Any, Callable
from datetime import datetime

from ..database.models import MessageEvent, Message
from ..database.operations import DatabaseManager, ChannelConfigManager
from ..ollama.client import OllamaClient, OllamaError, OllamaTimeoutError
from .integration import FilteredMessageProcessor
from .triggers import RateLimitManager, MessageGenerationTrigger
from .context import ContextWindowManager

logger = logging.getLogger(__name__)


class MessageProcessor:
    """
    Main message processing coordinator.
    
    Coordinates message filtering, database storage, generation triggers,
    and AI interaction for both spontaneous and response message generation.
    """
    
    def __init__(self, 
                 db_manager: DatabaseManager,
                 config_manager: ChannelConfigManager,
                 ollama_client: OllamaClient,
                 filtered_processor: FilteredMessageProcessor,
                 default_model: str):
        """
        Initialize MessageProcessor.
        
        Args:
            db_manager: Database manager instance
            config_manager: Channel configuration manager
            ollama_client: Ollama API client
            filtered_processor: Content filtering processor
            default_model: Default Ollama model name
        """
        self.db_manager = db_manager
        self.config_manager = config_manager
        self.ollama_client = ollama_client
        self.filtered_processor = filtered_processor
        self.default_model = default_model
        
        # Initialize rate limiting and triggers
        self.rate_limit_manager = RateLimitManager(config_manager, db_manager)
        self.generation_trigger = MessageGenerationTrigger(self.rate_limit_manager)
        
        # Initialize context window manager
        self.context_manager = ContextWindowManager(db_manager, config_manager)
        
        # IRC message sender callback (set by IRC client)
        self._message_sender: Optional[Callable] = None
        
        logger.info("MessageProcessor initialized")
    
    def set_message_sender(self, sender_callback: Callable) -> None:
        """
        Set the message sender callback for sending generated messages.
        
        Args:
            sender_callback: Async function to send messages to IRC
        """
        self._message_sender = sender_callback
    
    async def process_incoming_message(self, message_event: MessageEvent) -> None:
        """
        Process incoming chat message from IRC to database to generation.
        
        This is the main entry point for message processing flow:
        1. Apply content filtering
        2. Store filtered message in database
        3. Increment message count
        4. Check generation triggers
        5. Generate and send message if triggered
        
        Args:
            message_event: MessageEvent from IRC
        """
        try:
            channel = message_event.channel
            user_id = message_event.user_id
            
            # Step 1: Apply input content filtering
            filtered_content = self.filtered_processor.process_incoming_message(
                message_event.content, 
                user_id, 
                channel
            )
            
            if filtered_content is None:
                # Message was blocked by content filter
                logger.info(
                    "Message blocked by content filter, not storing",
                    extra={
                        "channel": channel,
                        "user_id": user_id,
                        "user_display_name": message_event.user_display_name
                    }
                )
                return
            
            # Update message content with filtered version
            message_event.content = filtered_content
            
            # Step 2: Store message in database
            success = await self.db_manager.store_message(message_event)
            if not success:
                logger.error(f"Failed to store message from {user_id} in {channel}")
                return
            
            # Step 3: Increment message count for channel
            new_count = await self.rate_limit_manager.increment_message_count(channel)
            
            logger.debug(
                "Message processed and stored",
                extra={
                    "channel": channel,
                    "user": message_event.user_display_name,
                    "new_message_count": new_count,
                    "content_length": len(filtered_content)
                }
            )
            
            # Step 4: Check if this is a mention and handle accordingly
            if getattr(message_event, 'is_mention', False):
                await self._handle_mention_response(message_event)
            else:
                # Step 5: Check spontaneous generation trigger
                await self._check_spontaneous_trigger(channel)
                
        except Exception as e:
            logger.error(f"Error processing incoming message: {e}")
    
    async def _handle_mention_response(self, message_event: MessageEvent) -> None:
        """
        Handle mention response generation.
        
        Args:
            message_event: MessageEvent containing the mention
        """
        try:
            channel = message_event.channel
            user_id = message_event.user_id
            user_name = message_event.user_display_name
            
            # Check if we can respond to this user (rate limiting)
            can_respond = await self.generation_trigger.check_mention_trigger(channel, user_id)
            
            if not can_respond:
                logger.debug(
                    "Mention response rate limited",
                    extra={
                        "channel": channel,
                        "user_id": user_id,
                        "user_name": user_name
                    }
                )
                return
            
            # Get mention content (the part after bot name)
            mention_content = getattr(message_event, 'mention_content', message_event.content)
            
            # Generate response
            await self._generate_response_message(channel, user_id, user_name, mention_content)
            
        except Exception as e:
            logger.error(f"Error handling mention response: {e}")
    
    async def _check_spontaneous_trigger(self, channel: str) -> None:
        """
        Check if spontaneous message generation should be triggered.
        
        Args:
            channel: Channel name to check
        """
        try:
            should_generate = await self.generation_trigger.check_spontaneous_trigger(channel)
            
            if should_generate:
                await self._generate_spontaneous_message(channel)
            
        except Exception as e:
            logger.error(f"Error checking spontaneous trigger for {channel}: {e}")
    
    async def _generate_spontaneous_message(self, channel: str) -> None:
        """
        Generate and send a spontaneous message.
        
        Args:
            channel: Channel name
        """
        try:
            start_time = datetime.now()
            
            # Get channel configuration for model selection
            config = await self.config_manager.get_config(channel)
            model = config.ollama_model or self.default_model
            
            # Build context window
            context_messages = await self.context_manager.build_context_window(
                channel, 
                config.context_limit,
                generation_type='spontaneous'
            )
            
            if not context_messages:
                logger.warning(f"No context available for spontaneous generation in {channel}")
                return
            
            # Generate message using Ollama
            generated_message = await self.ollama_client.generate_spontaneous_message(
                model, 
                context_messages
            )
            
            # Apply output content filtering
            filtered_message = self.filtered_processor.validate_generated_message(
                generated_message, 
                channel, 
                'spontaneous'
            )
            
            if filtered_message is None:
                logger.warning(
                    "Generated spontaneous message blocked by content filter",
                    extra={
                        "channel": channel,
                        "model": model,
                        "blocked_content": generated_message
                    }
                )
                return
            
            # Send message via IRC
            if self._message_sender:
                await self._message_sender(channel, filtered_message)
                
                # Record successful generation
                await self.generation_trigger.record_generation(channel, 'spontaneous')
                
                duration = (datetime.now() - start_time).total_seconds() * 1000
                logger.info(
                    "Spontaneous message generated and sent",
                    extra={
                        "channel": channel,
                        "model": model,
                        "response_time_ms": duration,
                        "message_length": len(filtered_message),
                        "context_size": len(context_messages)
                    }
                )
            else:
                logger.error("No message sender configured")
                
        except OllamaTimeoutError:
            logger.warning(f"Ollama timeout during spontaneous generation for {channel}")
        except OllamaError as e:
            logger.error(f"Ollama error during spontaneous generation for {channel}: {e}")
        except Exception as e:
            logger.error(f"Error generating spontaneous message for {channel}: {e}")
    
    async def _generate_response_message(self, channel: str, user_id: str, 
                                       user_name: str, user_input: str) -> None:
        """
        Generate and send a response message to a user mention.
        
        Args:
            channel: Channel name
            user_id: User ID who mentioned the bot
            user_name: Display name of the user
            user_input: The user's message content
        """
        try:
            start_time = datetime.now()
            
            # Get channel configuration for model selection
            config = await self.config_manager.get_config(channel)
            model = config.ollama_model or self.default_model
            
            # Build context window
            context_messages = await self.context_manager.build_context_window(
                channel, 
                config.context_limit,
                generation_type='response'
            )
            
            # Generate response using Ollama
            generated_response = await self.ollama_client.generate_response_message(
                model, 
                context_messages, 
                user_input, 
                user_name
            )
            
            # Apply output content filtering
            filtered_response = self.filtered_processor.validate_generated_message(
                generated_response, 
                channel, 
                'response'
            )
            
            if filtered_response is None:
                logger.warning(
                    "Generated response message blocked by content filter",
                    extra={
                        "channel": channel,
                        "user_id": user_id,
                        "user_name": user_name,
                        "model": model,
                        "blocked_content": generated_response
                    }
                )
                return
            
            # Send response via IRC
            if self._message_sender:
                await self._message_sender(channel, filtered_response)
                
                # Record successful response
                await self.generation_trigger.record_generation(channel, 'response', user_id)
                
                duration = (datetime.now() - start_time).total_seconds() * 1000
                logger.info(
                    "Response message generated and sent",
                    extra={
                        "channel": channel,
                        "user_id": user_id,
                        "user_name": user_name,
                        "model": model,
                        "response_time_ms": duration,
                        "message_length": len(filtered_response),
                        "context_size": len(context_messages)
                    }
                )
            else:
                logger.error("No message sender configured")
                
        except OllamaTimeoutError:
            logger.warning(f"Ollama timeout during response generation for {user_name} in {channel}")
        except OllamaError as e:
            logger.error(f"Ollama error during response generation for {user_name} in {channel}: {e}")
        except Exception as e:
            logger.error(f"Error generating response for {user_name} in {channel}: {e}")
    
    async def handle_moderation_event(self, event: Dict[str, Any]) -> None:
        """
        Handle moderation events (message deletions, user bans).
        
        Args:
            event: Moderation event dictionary
        """
        try:
            event_type = event.get('type')
            channel = event.get('channel')
            
            if event_type == 'clearmsg':
                # Single message deletion
                message_id = event.get('message_id')
                if message_id:
                    await self.db_manager.delete_message_by_id(message_id)
                    logger.info(
                        "Message deleted due to moderation",
                        extra={
                            "channel": channel,
                            "message_id": message_id,
                            "event_type": "clearmsg"
                        }
                    )
            
            elif event_type == 'clearchat_user':
                # User timeout/ban - delete all their messages
                user_id = event.get('user_id')
                if user_id:
                    await self.db_manager.delete_user_messages(channel, user_id)
                    logger.info(
                        "User messages deleted due to moderation",
                        extra={
                            "channel": channel,
                            "user_id": user_id,
                            "event_type": "clearchat_user"
                        }
                    )
            
            elif event_type == 'clearchat_all':
                # Full chat clear
                await self.db_manager.clear_channel_messages(channel)
                # Reset message count since all messages are gone
                await self.config_manager.reset_message_count(channel)
                logger.info(
                    "All messages cleared due to moderation",
                    extra={
                        "channel": channel,
                        "event_type": "clearchat_all"
                    }
                )
            
        except Exception as e:
            logger.error(f"Error handling moderation event: {e}")
    
    async def get_generation_status(self, channel: str, user_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Get current generation status for a channel.
        
        Args:
            channel: Channel name
            user_id: Optional user ID for response cooldown status
            
        Returns:
            Dictionary with generation status information
        """
        try:
            # Get rate limiting status
            rate_status = await self.rate_limit_manager.get_rate_limit_status(channel, user_id)
            
            # Get context information
            context_info = await self.context_manager.get_context_info(channel)
            
            # Combine status information
            status = {
                **rate_status,
                **context_info,
                "timestamp": datetime.now().isoformat()
            }
            
            return status
            
        except Exception as e:
            logger.error(f"Error getting generation status for {channel}: {e}")
            return {"error": str(e)}
    
    async def cleanup_old_data(self, retention_days: int = 7) -> bool:
        """
        Clean up old data (messages, metrics, cooldowns).
        
        Args:
            retention_days: Number of days to retain data
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            # This would be called periodically by the main application
            # Implementation depends on specific cleanup requirements
            
            # Clean up old user cooldowns
            await self.rate_limit_manager.cleanup_old_user_cooldowns(retention_days)
            
            logger.info(f"Data cleanup completed (retention: {retention_days} days)")
            return True
            
        except Exception as e:
            logger.error(f"Error during data cleanup: {e}")
            return False