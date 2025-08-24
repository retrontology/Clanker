"""
Twitch IRC client implementation.

This module handles IRC connections, message parsing,
and event handling for Twitch chat using TwitchIO.
"""

import asyncio
import logging
import re
from typing import List, Optional, Dict, Any, Callable, Set
from datetime import datetime, timedelta
from enum import Enum

import twitchio
from twitchio.ext import commands

from ..database.models import MessageEvent
from ..database.operations import DatabaseManager, ChannelConfigManager
from ..processing.filters import ContentFilter
from ..auth.manager import AuthenticationManager

logger = logging.getLogger(__name__)


class ConnectionState(Enum):
    """IRC connection states."""
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    RECONNECTING = "reconnecting"
    FAILED = "failed"


class IRCResilienceManager:
    """
    Manages IRC connection resilience with exponential backoff and banned channel tracking.
    """
    
    def __init__(self, max_reconnect_attempts: int = 0, base_delay: float = 5.0, max_delay: float = 300.0):
        """
        Initialize IRC resilience manager.
        
        Args:
            max_reconnect_attempts: Maximum reconnection attempts (0 = infinite)
            base_delay: Base delay for exponential backoff (seconds)
            max_delay: Maximum delay between reconnection attempts (seconds)
        """
        self.max_reconnect_attempts = max_reconnect_attempts
        self.base_delay = base_delay
        self.max_delay = max_delay
        
        self.state = ConnectionState.DISCONNECTED
        self.reconnect_attempts = 0
        self.last_connection_time: Optional[datetime] = None
        self.last_disconnection_time: Optional[datetime] = None
        self.connection_failures = 0
        
        # Banned channel tracking
        self.banned_channels: Set[str] = set()
        self.ban_timestamps: Dict[str, datetime] = {}
        self.ban_retry_delay = 3600  # 1 hour before retrying banned channels
        
        # Connection health tracking
        self.successful_connections = 0
        self.total_connection_attempts = 0
        self.uptime_start: Optional[datetime] = None
    
    def calculate_reconnect_delay(self) -> float:
        """
        Calculate exponential backoff delay with jitter.
        
        Returns:
            float: Delay in seconds
        """
        if self.reconnect_attempts == 0:
            return 0
        
        # Exponential backoff: base_delay * 2^(attempts - 1)
        delay = self.base_delay * (2 ** (self.reconnect_attempts - 1))
        
        # Cap at max_delay
        delay = min(delay, self.max_delay)
        
        # Add jitter (±20%) to prevent thundering herd
        import random
        jitter = delay * 0.2 * (random.random() - 0.5)
        delay = max(0, delay + jitter)
        
        return delay
    
    def should_attempt_reconnect(self) -> bool:
        """
        Check if reconnection should be attempted.
        
        Returns:
            bool: True if should attempt reconnection, False otherwise
        """
        if self.max_reconnect_attempts == 0:  # Infinite attempts
            return True
        
        return self.reconnect_attempts < self.max_reconnect_attempts
    
    def record_connection_attempt(self):
        """Record a connection attempt."""
        self.total_connection_attempts += 1
        self.reconnect_attempts += 1
        self.state = ConnectionState.CONNECTING
    
    def record_connection_success(self):
        """Record a successful connection."""
        self.state = ConnectionState.CONNECTED
        self.last_connection_time = datetime.now()
        self.successful_connections += 1
        self.connection_failures = 0
        self.uptime_start = datetime.now()
        
        # Reset reconnection counter on successful connection
        self.reconnect_attempts = 0
        
        logger.info(f"IRC connection established (attempt #{self.total_connection_attempts})")
    
    def record_connection_failure(self, error: Exception):
        """
        Record a connection failure.
        
        Args:
            error: The exception that caused the failure
        """
        self.state = ConnectionState.FAILED
        self.last_disconnection_time = datetime.now()
        self.connection_failures += 1
        self.uptime_start = None
        
        logger.error(f"IRC connection failed (attempt #{self.reconnect_attempts}): {error}")
    
    def record_disconnection(self, reason: str = "unknown"):
        """
        Record a disconnection.
        
        Args:
            reason: Reason for disconnection
        """
        self.state = ConnectionState.DISCONNECTED
        self.last_disconnection_time = datetime.now()
        self.uptime_start = None
        
        logger.warning(f"IRC connection lost: {reason}")
    
    def start_reconnection(self):
        """Start the reconnection process."""
        self.state = ConnectionState.RECONNECTING
        logger.info(f"Starting IRC reconnection (attempt #{self.reconnect_attempts + 1})")
    
    def add_banned_channel(self, channel: str, reason: str = "unknown"):
        """
        Add a channel to the banned list.
        
        Args:
            channel: Channel name that banned the bot
            reason: Reason for the ban
        """
        channel_lower = channel.lower()
        self.banned_channels.add(channel_lower)
        self.ban_timestamps[channel_lower] = datetime.now()
        
        logger.warning(f"Channel {channel} banned the bot: {reason}")
    
    def remove_banned_channel(self, channel: str):
        """
        Remove a channel from the banned list.
        
        Args:
            channel: Channel name to unban
        """
        channel_lower = channel.lower()
        self.banned_channels.discard(channel_lower)
        self.ban_timestamps.pop(channel_lower, None)
        
        logger.info(f"Channel {channel} removed from banned list")
    
    def is_channel_banned(self, channel: str) -> bool:
        """
        Check if a channel is currently banned.
        
        Args:
            channel: Channel name to check
            
        Returns:
            bool: True if banned, False otherwise
        """
        channel_lower = channel.lower()
        
        if channel_lower not in self.banned_channels:
            return False
        
        # Check if ban retry delay has passed
        ban_time = self.ban_timestamps.get(channel_lower)
        if ban_time:
            time_since_ban = (datetime.now() - ban_time).total_seconds()
            if time_since_ban >= self.ban_retry_delay:
                logger.info(f"Ban retry delay passed for {channel}, removing from banned list")
                self.remove_banned_channel(channel)
                return False
        
        return True
    
    def get_allowed_channels(self, channels: List[str]) -> List[str]:
        """
        Filter out banned channels from a list.
        
        Args:
            channels: List of channel names
            
        Returns:
            List of non-banned channels
        """
        allowed = []
        for channel in channels:
            if not self.is_channel_banned(channel):
                allowed.append(channel)
            else:
                logger.debug(f"Skipping banned channel: {channel}")
        
        return allowed
    
    def get_connection_stats(self) -> Dict[str, Any]:
        """
        Get connection statistics.
        
        Returns:
            Dict containing connection stats
        """
        now = datetime.now()
        stats = {
            'state': self.state.value,
            'reconnect_attempts': self.reconnect_attempts,
            'total_connection_attempts': self.total_connection_attempts,
            'successful_connections': self.successful_connections,
            'connection_failures': self.connection_failures,
            'banned_channels': list(self.banned_channels),
        }
        
        if self.last_connection_time:
            stats['last_connection_time'] = self.last_connection_time.isoformat()
        
        if self.last_disconnection_time:
            stats['last_disconnection_time'] = self.last_disconnection_time.isoformat()
            stats['time_since_disconnection'] = (now - self.last_disconnection_time).total_seconds()
        
        if self.uptime_start:
            stats['uptime_seconds'] = (now - self.uptime_start).total_seconds()
        
        return stats


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
        
        # Connection resilience management
        self.resilience_manager = IRCResilienceManager(
            max_reconnect_attempts=0,  # Infinite reconnection attempts
            base_delay=5.0,
            max_delay=300.0
        )
        self._connected_channels: set = set()
        self._target_channels = set(initial_channels)  # Channels we want to be in
        self._reconnection_task: Optional[asyncio.Task] = None
        
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
        
        # Record successful connection
        self.resilience_manager.record_connection_success()
        
        # Cancel any ongoing reconnection task
        if self._reconnection_task and not self._reconnection_task.done():
            self._reconnection_task.cancel()
            self._reconnection_task = None
    
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
        """Handle connection errors with resilience."""
        logger.error(f"IRC connection error: {error}")
        if data:
            logger.debug(f"Error data: {data}")
        
        # Record the failure
        self.resilience_manager.record_connection_failure(error)
        
        # Check if this is a ban-related error
        if self._is_ban_error(error, data):
            await self._handle_ban_error(error, data)
        
        # Start reconnection if not already in progress
        if not self._reconnection_task or self._reconnection_task.done():
            self._reconnection_task = asyncio.create_task(self._reconnection_loop())
    
    def _is_ban_error(self, error: Exception, data: str = None) -> bool:
        """
        Check if error indicates the bot was banned from a channel.
        
        Args:
            error: The exception that occurred
            data: Optional error data
            
        Returns:
            bool: True if this appears to be a ban error
        """
        error_str = str(error).lower()
        data_str = (data or "").lower()
        
        ban_indicators = [
            'banned', 'ban', 'msg_banned', 'msg_channel_banned',
            'forbidden', 'access denied', 'not allowed'
        ]
        
        return any(indicator in error_str or indicator in data_str for indicator in ban_indicators)
    
    async def _handle_ban_error(self, error: Exception, data: str = None):
        """
        Handle ban-related errors by tracking banned channels.
        
        Args:
            error: The exception that occurred
            data: Optional error data
        """
        # Try to extract channel name from error or data
        channel = self._extract_channel_from_error(error, data)
        
        if channel:
            self.resilience_manager.add_banned_channel(channel, str(error))
            # Remove from target channels temporarily
            self._target_channels.discard(channel)
        else:
            logger.warning(f"Could not identify banned channel from error: {error}")
    
    def _extract_channel_from_error(self, error: Exception, data: str = None) -> Optional[str]:
        """
        Try to extract channel name from error message or data.
        
        Args:
            error: The exception that occurred
            data: Optional error data
            
        Returns:
            Channel name if found, None otherwise
        """
        text_to_search = f"{str(error)} {data or ''}"
        
        # Look for channel patterns like #channelname or "channelname"
        import re
        
        # Pattern for #channelname
        channel_match = re.search(r'#(\w+)', text_to_search)
        if channel_match:
            return channel_match.group(1)
        
        # Pattern for quoted channel name
        quoted_match = re.search(r'["\'](\w+)["\']', text_to_search)
        if quoted_match:
            return quoted_match.group(1)
        
        return None
    
    async def _reconnection_loop(self):
        """
        Main reconnection loop with exponential backoff.
        """
        while self.resilience_manager.should_attempt_reconnect():
            try:
                # Check if we're already connected
                if self.resilience_manager.state == ConnectionState.CONNECTED:
                    logger.debug("Already connected, stopping reconnection loop")
                    break
                
                # Calculate delay
                delay = self.resilience_manager.calculate_reconnect_delay()
                if delay > 0:
                    logger.info(f"Waiting {delay:.2f}s before reconnection attempt")
                    await asyncio.sleep(delay)
                
                # Start reconnection attempt
                self.resilience_manager.start_reconnection()
                await self._attempt_reconnection()
                
                # If we get here, reconnection was successful
                break
                
            except asyncio.CancelledError:
                logger.info("Reconnection loop cancelled")
                break
            except Exception as e:
                self.resilience_manager.record_connection_failure(e)
                logger.error(f"Reconnection attempt failed: {e}")
                
                # Continue the loop for next attempt
                continue
        
        if not self.resilience_manager.should_attempt_reconnect():
            logger.error("Maximum reconnection attempts reached, giving up")
            self.resilience_manager.state = ConnectionState.FAILED
    
    async def _attempt_reconnection(self):
        """
        Attempt to reconnect to IRC and rejoin channels.
        """
        self.resilience_manager.record_connection_attempt()
        
        try:
            # Close existing connection if any
            if hasattr(self, '_websocket') and self._websocket:
                await self._websocket.close()
            
            # Filter out banned channels
            allowed_channels = self.resilience_manager.get_allowed_channels(list(self._target_channels))
            
            if not allowed_channels:
                logger.warning("No allowed channels to connect to (all banned)")
                # Wait a bit and add channels back for retry
                await asyncio.sleep(60)
                self._target_channels.update(self.resilience_manager.banned_channels)
                allowed_channels = list(self._target_channels)
            
            logger.info(f"Attempting to reconnect to channels: {allowed_channels}")
            
            # Recreate the bot connection
            # Note: TwitchIO doesn't have a direct reconnect method, so we simulate it
            # by updating the initial channels and calling start() again
            self.initial_channels = allowed_channels
            
            # This will trigger event_ready when successful
            await self.start()
            
        except Exception as e:
            logger.error(f"Reconnection attempt failed: {e}")
            raise
    
    async def join_channel(self, channel: str) -> bool:
        """
        Join a new channel with ban checking.
        
        Args:
            channel: Channel name to join
            
        Returns:
            True if successful, False otherwise
        """
        # Check if channel is banned
        if self.resilience_manager.is_channel_banned(channel):
            logger.warning(f"Cannot join banned channel: {channel}")
            return False
        
        try:
            await self.join_channels([channel])
            self._target_channels.add(channel)
            logger.info(f"Joined new channel: {channel}")
            return True
        except Exception as e:
            logger.error(f"Failed to join channel {channel}: {e}")
            
            # Check if this was a ban error
            if self._is_ban_error(e):
                self.resilience_manager.add_banned_channel(channel, str(e))
            
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
            self._target_channels.discard(channel)
            logger.info(f"Left channel: {channel}")
            return True
        except Exception as e:
            logger.error(f"Failed to leave channel {channel}: {e}")
            return False
    
    def get_connected_channels(self) -> List[str]:
        """Get list of currently connected channels."""
        return list(self._connected_channels)
    
    def get_target_channels(self) -> List[str]:
        """Get list of channels we want to be connected to."""
        return list(self._target_channels)
    
    def get_banned_channels(self) -> List[str]:
        """Get list of channels that have banned the bot."""
        return list(self.resilience_manager.banned_channels)
    
    def unban_channel(self, channel: str) -> bool:
        """
        Remove a channel from the banned list and add it back to targets.
        
        Args:
            channel: Channel name to unban
            
        Returns:
            True if channel was unbanned, False if it wasn't banned
        """
        if self.resilience_manager.is_channel_banned(channel):
            self.resilience_manager.remove_banned_channel(channel)
            self._target_channels.add(channel)
            return True
        return False
    
    def get_connection_status(self) -> Dict[str, Any]:
        """
        Get comprehensive connection status information.
        
        Returns:
            Dict containing connection status details
        """
        stats = self.resilience_manager.get_connection_stats()
        stats.update({
            'bot_username': self.bot_username,
            'connected_channels': list(self._connected_channels),
            'target_channels': list(self._target_channels),
            'is_connected': self.resilience_manager.state == ConnectionState.CONNECTED,
            'reconnection_active': self._reconnection_task is not None and not self._reconnection_task.done(),
        })
        
        return stats
    
    async def force_reconnect(self) -> bool:
        """
        Force a reconnection attempt.
        
        Returns:
            True if reconnection was initiated, False otherwise
        """
        try:
            logger.info("Forcing IRC reconnection")
            
            # Cancel existing reconnection task
            if self._reconnection_task and not self._reconnection_task.done():
                self._reconnection_task.cancel()
            
            # Record disconnection and start new reconnection
            self.resilience_manager.record_disconnection("forced_reconnect")
            self._reconnection_task = asyncio.create_task(self._reconnection_loop())
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to initiate forced reconnection: {e}")
            return False
    
    def is_connection_healthy(self) -> bool:
        """
        Check if IRC connection is healthy.
        
        Returns:
            bool: True if connection is healthy, False otherwise
        """
        return (
            self.resilience_manager.state == ConnectionState.CONNECTED and
            len(self._connected_channels) > 0 and
            (not self._reconnection_task or self._reconnection_task.done())
        )
    
    async def close(self) -> None:
        """Close the IRC connection and cleanup resources."""
        try:
            logger.info("Closing IRC connection")
            
            # Cancel reconnection task if running
            if self._reconnection_task and not self._reconnection_task.done():
                self._reconnection_task.cancel()
                try:
                    await self._reconnection_task
                except asyncio.CancelledError:
                    pass
            
            # Record disconnection
            self.resilience_manager.record_disconnection("manual_close")
            
            # Close the connection
            await super().close()
            
        except Exception as e:
            logger.error(f"Error closing IRC connection: {e}")


