"""
Twitch IRC client implementation.

This module handles IRC connections, message parsing,
and event handling for Twitch chat using TwitchIO.
"""

import asyncio
import logging
import re
from typing import List, Optional, Dict, Any, Callable
from datetime import datetime

import twitchio
from twitchio.ext import commands

from ..database.models import MessageEvent
from ..database.operations import DatabaseManager, ChannelConfigManager
from ..processing.filters import ContentFilter
from ..auth.manager import AuthenticationManager

logger = logging.getLogger(__name__)


class TwitchIRCClient(commands.Bot):
    """
    TwitchIO bot client with multi-channel support and automatic reconnection.
    
    Handles message events, moderation events, and connection management
    with bot detection logic to filter out bot messages and system notifications.
    """
    
    def __init__(self, 
                 token: str, 
                 bot_username: str, 
                 initial_channels: List[str],
                 db_manager: DatabaseManager,
                 config_manager: ChannelConfigManager,
                 content_filter: ContentFilter,
                 known_bots: Optional[List[str]] = None):
        """
        Initialize TwitchIRCClient.
        
        Args:
            token: OAuth access token for authentication
            bot_username: Username of the bot account
            initial_channels: List of channels to join on startup
            db_manager: Database manager instance
            config_manager: Channel configuration manager
            content_filter: Content filtering instance
            known_bots: List of known bot usernames to ignore
        """
        # Initialize TwitchIO bot with required parameters
        super().__init__(
            token=token,
            prefix='!',  # Command prefix (we'll handle !clank commands)
            initial_channels=initial_channels
        )
        
        self.bot_username = bot_username.lower()
        self.db_manager = db_manager
        self.config_manager = config_manager
        self.content_filter = content_filter
        
        # Known bot usernames to ignore (case-insensitive)
        self.known_bots = set((known_bots or []))
        self.known_bots.add(self.bot_username)  # Always ignore our own messages
        
        # Add common Twitch bots
        default_bots = {
            'nightbot', 'streamelements', 'streamlabs', 'moobot', 'fossabot',
            'wizebot', 'botisimo', 'cloudbot', 'ankhbot', 'deepbot',
            'phantombot', 'coebot', 'vivbot', 'ohbot', 'tipeeebot'
        }
        self.known_bots.update(default_bots)
        
        # Connection state tracking
        self._connected_channels: set = set()
        self._reconnect_attempts = 0
        self._max_reconnect_attempts = 10
        self._reconnect_delay = 5.0  # Start with 5 seconds
        
        # Event handlers for external components
        self._message_handlers: List[Callable] = []
        self._moderation_handlers: List[Callable] = []
        
        logger.info(f"TwitchIRCClient initialized for bot: {bot_username}")
    
    def add_message_handler(self, handler: Callable) -> None:
        """Add external message handler."""
        self._message_handlers.append(handler)
    
    def add_moderation_handler(self, handler: Callable) -> None:
        """Add external moderation event handler."""
        self._moderation_handlers.append(handler)
    
    async def event_ready(self) -> None:
        """Called when the bot is ready and connected."""
        logger.info(f"Bot {self.bot_username} is ready and connected to Twitch IRC")
        logger.info(f"Connected to channels: {[ch.name for ch in self.connected_channels]}")
        
        # Track connected channels
        self._connected_channels = {ch.name for ch in self.connected_channels}
        
        # Reset reconnection counter on successful connection
        self._reconnect_attempts = 0
        self._reconnect_delay = 5.0
    
    async def event_message(self, message: twitchio.Message) -> None:
        """
        Handle incoming messages with filtering and routing.
        
        Args:
            message: TwitchIO message object
        """
        try:
            # Skip if message is None or has no content
            if not message or not message.content:
                return
            
            # Skip if message is from this bot or other known bots
            if self.is_bot_message(message.author.name):
                return
            
            # Skip system messages
            if self.is_system_message(message):
                return
            
            # Create MessageEvent from TwitchIO message
            message_event = MessageEvent.from_twitchio_message(message)
            
            # Handle chat commands first (before content filtering)
            if message.content.startswith('!clank'):
                await self.handle_chat_command(message)
                return
            
            # Apply content filtering
            filtered_content = self.content_filter.filter_input(message.content)
            if filtered_content is None:
                logger.warning(
                    "Message blocked by content filter",
                    extra={
                        "channel": message.channel.name,
                        "user": message.author.display_name,
                        "message_id": message.id,
                        "original_content": message.content
                    }
                )
                return
            
            # Update message event with filtered content
            message_event.content = filtered_content
            
            # Check if this is a mention of the bot
            is_bot_mention = self.is_mention(message.content)
            
            # Store message in database
            if await self.db_manager.store_message(message_event):
                # Increment message count for the channel (only for non-mention messages)
                if not is_bot_mention:
                    await self.config_manager.increment_message_count(message.channel.name)
                
                # Notify external message handlers with mention information
                for handler in self._message_handlers:
                    try:
                        # Add mention information to the message event
                        message_event.is_mention = is_bot_mention
                        if is_bot_mention:
                            message_event.mention_content = self.extract_mention_content(message.content)
                        
                        await handler(message_event)
                    except Exception as e:
                        logger.error(f"Error in message handler: {e}")
            
        except Exception as e:
            logger.error(f"Error processing message: {e}")
    
    async def event_raw_data(self, data: str) -> None:
        """
        Handle raw IRC data for moderation events.
        
        Args:
            data: Raw IRC message data
        """
        try:
            # Parse CLEARMSG events (single message deletion)
            if 'CLEARMSG' in data:
                await self._handle_clearmsg_raw(data)
            
            # Parse CLEARCHAT events (user timeout/ban or full chat clear)
            elif 'CLEARCHAT' in data:
                await self._handle_clearchat_raw(data)
                
        except Exception as e:
            logger.error(f"Error processing raw IRC data: {e}")
    
    async def _handle_clearmsg_raw(self, data: str) -> None:
        """Handle CLEARMSG raw IRC data."""
        try:
            # Parse CLEARMSG format: @target-msg-id=<msg_id> :tmi.twitch.tv CLEARMSG #<channel> :<message>
            match = re.search(r'@.*?target-msg-id=([^;\s]+).*?CLEARMSG\s+#(\w+)', data)
            if match:
                message_id = match.group(1)
                channel = match.group(2)
                
                await self.handle_clearmsg(channel, message_id)
                
        except Exception as e:
            logger.error(f"Error parsing CLEARMSG: {e}")
    
    async def _handle_clearchat_raw(self, data: str) -> None:
        """Handle CLEARCHAT raw IRC data."""
        try:
            # Parse CLEARCHAT format: @ban-duration=<duration>;target-user-id=<user_id> :tmi.twitch.tv CLEARCHAT #<channel> :<username>
            # Or for full clear: :tmi.twitch.tv CLEARCHAT #<channel>
            
            channel_match = re.search(r'CLEARCHAT\s+#(\w+)', data)
            if not channel_match:
                return
            
            channel = channel_match.group(1)
            
            # Check if it's a user-specific clear
            user_id_match = re.search(r'target-user-id=([^;\s]+)', data)
            if user_id_match:
                user_id = user_id_match.group(1)
                await self.handle_clearchat_user(channel, user_id)
            else:
                # Full chat clear
                await self.handle_clearchat_all(channel)
                
        except Exception as e:
            logger.error(f"Error parsing CLEARCHAT: {e}")
    
    async def handle_clearmsg(self, channel: str, message_id: str) -> None:
        """
        Handle single message deletion (CLEARMSG event).
        
        Args:
            channel: Channel name
            message_id: ID of the message to delete
        """
        try:
            success = await self.db_manager.delete_message_by_id(message_id)
            
            if success:
                logger.info(f"Deleted message {message_id} from {channel}")
            else:
                logger.warning(f"Failed to delete message {message_id} from {channel}")
            
            # Notify moderation handlers
            for handler in self._moderation_handlers:
                try:
                    await handler({
                        'type': 'clearmsg',
                        'channel': channel,
                        'message_id': message_id
                    })
                except Exception as e:
                    logger.error(f"Error in moderation handler: {e}")
                    
        except Exception as e:
            logger.error(f"Error handling CLEARMSG for {message_id} in {channel}: {e}")
    
    async def handle_clearchat_user(self, channel: str, user_id: str) -> None:
        """
        Handle user timeout/ban (CLEARCHAT user event).
        
        Args:
            channel: Channel name
            user_id: ID of the user whose messages to delete
        """
        try:
            success = await self.db_manager.delete_user_messages(channel, user_id)
            
            if success:
                logger.info(f"Deleted all messages from user {user_id} in {channel}")
            else:
                logger.warning(f"Failed to delete messages from user {user_id} in {channel}")
            
            # Notify moderation handlers
            for handler in self._moderation_handlers:
                try:
                    await handler({
                        'type': 'clearchat_user',
                        'channel': channel,
                        'user_id': user_id
                    })
                except Exception as e:
                    logger.error(f"Error in moderation handler: {e}")
                    
        except Exception as e:
            logger.error(f"Error handling CLEARCHAT user {user_id} in {channel}: {e}")
    
    async def handle_clearchat_all(self, channel: str) -> None:
        """
        Handle full chat clear (CLEARCHAT all event).
        
        Args:
            channel: Channel name
        """
        try:
            success = await self.db_manager.clear_channel_messages(channel)
            
            if success:
                logger.info(f"Cleared all messages in {channel}")
            else:
                logger.warning(f"Failed to clear messages in {channel}")
            
            # Notify moderation handlers
            for handler in self._moderation_handlers:
                try:
                    await handler({
                        'type': 'clearchat_all',
                        'channel': channel
                    })
                except Exception as e:
                    logger.error(f"Error in moderation handler: {e}")
                    
        except Exception as e:
            logger.error(f"Error handling CLEARCHAT all in {channel}: {e}")
    
    def is_bot_message(self, username: str) -> bool:
        """
        Check if message should be ignored (from bots).
        
        Args:
            username: Username to check
            
        Returns:
            True if message is from a bot, False otherwise
        """
        if not username:
            return True
        
        username_lower = username.lower()
        return username_lower in self.known_bots
    
    def is_system_message(self, message: twitchio.Message) -> bool:
        """
        Check if message is from Twitch system.
        
        Args:
            message: TwitchIO message object
            
        Returns:
            True if message is from system, False otherwise
        """
        # System messages in TwitchIO typically don't have author.id or are special types
        if not message.author or not message.author.id:
            return True
        
        # Check for system usernames
        system_users = {'twitchnotify', 'jtv', 'tmi'}
        if message.author.name.lower() in system_users:
            return True
        
        return False
    
    async def handle_chat_command(self, message: twitchio.Message) -> None:
        """
        Handle !clank chat commands.
        
        Args:
            message: TwitchIO message object containing the command
        """
        try:
            # Check user permissions (broadcaster or moderator)
            if not self._is_authorized_user(message):
                logger.info(
                    "Unauthorized user attempted !clank command",
                    extra={
                        "channel": message.channel.name,
                        "user": message.author.display_name,
                        "command": message.content
                    }
                )
                return
            
            # Parse command
            parts = message.content.split()
            if len(parts) < 2:
                await self._send_command_help(message.channel.name)
                return
            
            command = parts[1].lower()
            
            # Handle different command types
            if command in ['threshold', 'spontaneous', 'response', 'context', 'model']:
                await self._handle_config_command(message, command, parts[2:])
            elif command == 'status':
                await self._handle_status_command(message)
            elif command == 'help':
                await self._send_command_help(message.channel.name)
            else:
                await self.send_message(
                    message.channel.name,
                    f"Unknown command: {command}. Use !clank help for available commands."
                )
                
        except Exception as e:
            logger.error(f"Error handling chat command: {e}")
            await self.send_message(
                message.channel.name,
                "Sorry, there was an error processing that command."
            )
    
    def _is_authorized_user(self, message: twitchio.Message) -> bool:
        """
        Check if user is authorized to use !clank commands.
        
        Args:
            message: TwitchIO message object
            
        Returns:
            True if user is authorized, False otherwise
        """
        if not message.author or not message.author.badges:
            return False
        
        badges = message.author.badges
        
        # Check for broadcaster or moderator badges
        return 'broadcaster' in badges or 'moderator' in badges
    
    async def _handle_config_command(self, message: twitchio.Message, setting: str, args: List[str]) -> None:
        """
        Handle configuration commands.
        
        Args:
            message: TwitchIO message object
            setting: Setting name to modify
            args: Command arguments
        """
        channel = message.channel.name
        
        try:
            if not args:
                # Show current value
                config = await self.config_manager.get_config(channel)
                current_value = getattr(config, f"{setting}_cooldown" if setting in ['spontaneous', 'response'] else 
                                      "message_threshold" if setting == "threshold" else
                                      "context_limit" if setting == "context" else
                                      "ollama_model" if setting == "model" else setting)
                
                if setting == 'model' and current_value is None:
                    await self.send_message(channel, f"Current {setting}: using global default")
                else:
                    await self.send_message(channel, f"Current {setting}: {current_value}")
            else:
                # Set new value
                new_value = args[0]
                
                # Validate and convert value
                if setting in ['threshold', 'spontaneous', 'response', 'context']:
                    try:
                        new_value = int(new_value)
                        if new_value < 0:
                            await self.send_message(channel, f"Error: {setting} must be non-negative")
                            return
                    except ValueError:
                        await self.send_message(channel, f"Error: {setting} must be a number")
                        return
                
                # Map setting names to database column names
                db_key = {
                    'threshold': 'message_threshold',
                    'spontaneous': 'spontaneous_cooldown',
                    'response': 'response_cooldown',
                    'context': 'context_limit',
                    'model': 'ollama_model'
                }[setting]
                
                # Update configuration
                success = await self.config_manager.update_config(channel, db_key, new_value)
                
                if success:
                    await self.send_message(channel, f"Updated {setting} to: {new_value}")
                    logger.info(
                        "Configuration updated via chat command",
                        extra={
                            "channel": channel,
                            "setting": setting,
                            "new_value": new_value,
                            "user": message.author.display_name
                        }
                    )
                else:
                    await self.send_message(channel, f"Failed to update {setting}")
                    
        except Exception as e:
            logger.error(f"Error handling config command {setting}: {e}")
            await self.send_message(channel, f"Error updating {setting}")
    
    async def _handle_status_command(self, message: twitchio.Message) -> None:
        """
        Handle status command to show bot health and configuration.
        
        Args:
            message: TwitchIO message object
        """
        channel = message.channel.name
        
        try:
            config = await self.config_manager.get_config(channel)
            
            # Get recent message count
            recent_count = await self.db_manager.count_recent_messages(channel, hours=1)
            
            status_msg = (
                f"Bot Status - Messages: {config.message_count}/{config.message_threshold}, "
                f"Recent (1h): {recent_count}, "
                f"Spontaneous cooldown: {config.spontaneous_cooldown}s, "
                f"Response cooldown: {config.response_cooldown}s"
            )
            
            await self.send_message(channel, status_msg)
            
        except Exception as e:
            logger.error(f"Error handling status command: {e}")
            await self.send_message(channel, "Error retrieving status")
    
    async def _send_command_help(self, channel: str) -> None:
        """
        Send help message with available commands.
        
        Args:
            channel: Channel to send help to
        """
        help_msg = (
            "!clank commands: threshold [num], spontaneous [seconds], response [seconds], "
            "context [num], model [name], status, help"
        )
        await self.send_message(channel, help_msg)
    
    def is_mention(self, message_content: str) -> bool:
        """
        Check if message is a mention of the bot.
        
        Args:
            message_content: Message content to check
            
        Returns:
            True if message mentions the bot, False otherwise
        """
        if not message_content:
            return False
        
        content_lower = message_content.lower().strip()
        bot_name_lower = self.bot_username.lower()
        
        # Check for @botname at start
        if content_lower.startswith(f"@{bot_name_lower}"):
            return True
        
        # Check for botname at start (without @)
        if content_lower.startswith(bot_name_lower):
            # Make sure it's followed by whitespace or punctuation (not part of another word)
            if len(content_lower) == len(bot_name_lower):
                return True
            next_char = content_lower[len(bot_name_lower)]
            if not next_char.isalnum() and next_char != '_':
                return True
        
        return False
    
    def extract_mention_content(self, message_content: str) -> str:
        """
        Extract the content after a bot mention.
        
        Args:
            message_content: Full message content
            
        Returns:
            Content after the mention, stripped of whitespace
        """
        if not self.is_mention(message_content):
            return message_content
        
        content_lower = message_content.lower().strip()
        bot_name_lower = self.bot_username.lower()
        
        # Remove @botname or botname from the start
        if content_lower.startswith(f"@{bot_name_lower}"):
            remaining = message_content[len(bot_name_lower) + 1:].strip()
        elif content_lower.startswith(bot_name_lower):
            remaining = message_content[len(bot_name_lower):].strip()
        else:
            remaining = message_content
        
        # Remove common punctuation after bot name
        if remaining.startswith((':',  ',', '!', '?', '.')):
            remaining = remaining[1:].strip()
        
        return remaining
    
    async def send_message(self, channel: str, content: str) -> bool:
        """
        Send a message to a channel.
        
        Args:
            channel: Channel name to send message to
            content: Message content to send
            
        Returns:
            True if successful, False otherwise
        """
        try:
            # Get channel object
            channel_obj = self.get_channel(channel)
            if not channel_obj:
                logger.error(f"Channel {channel} not found or not connected")
                return False
            
            # Apply output content filtering
            filtered_content = self.content_filter.filter_output(content)
            if filtered_content is None:
                logger.warning(
                    "Bot message blocked by output filter",
                    extra={
                        "channel": channel,
                        "original_content": content
                    }
                )
                return False
            
            # Send the message
            await channel_obj.send(filtered_content)
            
            logger.info(
                "Message sent successfully",
                extra={
                    "channel": channel,
                    "content": filtered_content
                }
            )
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to send message to {channel}: {e}")
            return False
    
    async def event_channel_joined(self, channel: twitchio.Channel) -> None:
        """Called when the bot joins a channel."""
        logger.info(f"Joined channel: {channel.name}")
        self._connected_channels.add(channel.name)
    
    async def event_channel_left(self, channel: twitchio.Channel) -> None:
        """Called when the bot leaves a channel."""
        logger.info(f"Left channel: {channel.name}")
        self._connected_channels.discard(channel.name)
    
    async def event_error(self, error: Exception, data: str = None) -> None:
        """Handle connection errors."""
        logger.error(f"IRC connection error: {error}")
        if data:
            logger.debug(f"Error data: {data}")
    
    async def join_channel(self, channel: str) -> bool:
        """
        Join a new channel.
        
        Args:
            channel: Channel name to join
            
        Returns:
            True if successful, False otherwise
        """
        try:
            await self.join_channels([channel])
            logger.info(f"Joined new channel: {channel}")
            return True
        except Exception as e:
            logger.error(f"Failed to join channel {channel}: {e}")
            return False
    
    async def leave_channel(self, channel: str) -> bool:
        """
        Leave a channel.
        
        Args:
            channel: Channel name to leave
            
        Returns:
            True if successful, False otherwise
        """
        try:
            await self.part_channels([channel])
            logger.info(f"Left channel: {channel}")
            return True
        except Exception as e:
            logger.error(f"Failed to leave channel {channel}: {e}")
            return False
    
    def get_connected_channels(self) -> List[str]:
        """Get list of currently connected channels."""
        return list(self._connected_channels)
    
    async def close(self) -> None:
        """Close the IRC connection and cleanup resources."""
        try:
            logger.info("Closing IRC connection")
            await super().close()
        except Exception as e:
            logger.error(f"Error closing IRC connection: {e}")


