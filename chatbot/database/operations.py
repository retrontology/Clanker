"""
Database CRUD operations.

This module implements database operations for message storage,
retrieval, and management with support for both SQLite and MySQL.
"""

import sqlite3
import mysql.connector
from mysql.connector import pooling
import asyncio
import logging
from typing import List, Optional, Dict, Any, Union
from datetime import datetime, timedelta
from contextlib import asynccontextmanager
import time

from .models import Message, MessageEvent, ChannelConfig, UserResponseCooldown, BotMetric, AuthToken
from .migrations import DatabaseMigrations

logger = logging.getLogger(__name__)


# Function moved after DatabaseManager class definition


class DatabaseManager:
    """Manages database connections and operations with factory pattern for SQLite/MySQL."""
    
    def __init__(self, db_type: str = "sqlite", **connection_params):
        """
        Initialize DatabaseManager with factory pattern.
        
        Args:
            db_type: Either 'sqlite' or 'mysql'
            **connection_params: Database connection parameters
        """
        self.db_type = db_type.lower()
        self.connection_params = connection_params
        self.connection_pool = None
        self._retry_count = 0
        self._max_retries = 3
        self._retry_delay = 1.0  # Start with 1 second delay
        
        # Initialize database schema
        self.migrations = DatabaseMigrations(db_type, connection_params)
    
    async def initialize(self) -> bool:
        """
        Initialize database connection and schema.
        
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            # Initialize schema first
            if not await self.migrations.initialize_database():
                logger.error("Failed to initialize database schema")
                return False
            
            # Set up connection pool for MySQL
            if self.db_type == 'mysql':
                await self._setup_mysql_pool()
            
            logger.info(f"Database manager initialized ({self.db_type})")
            return True
            
        except Exception as e:
            logger.error(f"Database initialization failed: {e}")
            return False
    
    async def _setup_mysql_pool(self):
        """Set up MySQL connection pool."""
        try:
            pool_config = {
                'pool_name': 'chatbot_pool',
                'pool_size': 5,
                'pool_reset_session': True,
                'host': self.connection_params['host'],
                'port': self.connection_params.get('port', 3306),
                'user': self.connection_params['user'],
                'password': self.connection_params['password'],
                'database': self.connection_params['database'],
                'autocommit': True
            }
            
            self.connection_pool = pooling.MySQLConnectionPool(**pool_config)
            logger.info("MySQL connection pool created")
            
        except Exception as e:
            logger.error(f"Failed to create MySQL connection pool: {e}")
            raise
    
    @asynccontextmanager
    async def get_connection(self):
        """
        Get database connection with retry logic and graceful failure handling.
        
        Yields:
            Database connection object
        """
        connection = None
        try:
            if self.db_type == 'sqlite':
                database_path = self.connection_params.get('database_url', './chatbot.db')
                connection = sqlite3.connect(database_path)
                connection.row_factory = sqlite3.Row
                yield connection
                
            elif self.db_type == 'mysql':
                if self.connection_pool:
                    connection = self.connection_pool.get_connection()
                else:
                    connection = mysql.connector.connect(
                        host=self.connection_params['host'],
                        port=self.connection_params.get('port', 3306),
                        user=self.connection_params['user'],
                        password=self.connection_params['password'],
                        database=self.connection_params['database']
                    )
                yield connection
                
        except Exception as e:
            logger.error(f"Database connection error: {e}")
            await self._handle_connection_error(e)
            raise
        finally:
            if connection:
                try:
                    connection.close()
                except:
                    pass
    
    async def _handle_connection_error(self, error: Exception):
        """Handle connection errors with exponential backoff retry."""
        self._retry_count += 1
        
        if self._retry_count <= self._max_retries:
            delay = self._retry_delay * (2 ** (self._retry_count - 1))
            logger.warning(f"Database connection failed, retrying in {delay}s (attempt {self._retry_count}/{self._max_retries})")
            await asyncio.sleep(delay)
        else:
            logger.error(f"Database connection failed after {self._max_retries} attempts")
            self._retry_count = 0  # Reset for next operation
    
    async def store_message(self, message_event: MessageEvent) -> bool:
        """
        Store a message in the database.
        
        Args:
            message_event: MessageEvent to store
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            async with self.get_connection() as conn:
                cursor = conn.cursor()
                
                if self.db_type == 'sqlite':
                    cursor.execute("""
                        INSERT OR IGNORE INTO messages 
                        (message_id, channel, user_id, user_display_name, message_content, timestamp)
                        VALUES (?, ?, ?, ?, ?, ?)
                    """, (
                        message_event.message_id,
                        message_event.channel,
                        message_event.user_id,
                        message_event.user_display_name,
                        message_event.content,
                        message_event.timestamp
                    ))
                    conn.commit()
                    
                elif self.db_type == 'mysql':
                    cursor.execute("""
                        INSERT IGNORE INTO messages 
                        (message_id, channel, user_id, user_display_name, message_content, timestamp)
                        VALUES (%s, %s, %s, %s, %s, %s)
                    """, (
                        message_event.message_id,
                        message_event.channel,
                        message_event.user_id,
                        message_event.user_display_name,
                        message_event.content,
                        message_event.timestamp
                    ))
                
                self._retry_count = 0  # Reset retry count on success
                return True
                
        except Exception as e:
            logger.error(f"Failed to store message: {e}")
            return False
    
    async def get_recent_messages(self, channel: str, limit: int = 200) -> List[Message]:
        """
        Retrieve recent messages for a channel.
        
        Args:
            channel: Channel name
            limit: Maximum number of messages to retrieve
            
        Returns:
            List of Message objects
        """
        try:
            async with self.get_connection() as conn:
                cursor = conn.cursor()
                
                if self.db_type == 'sqlite':
                    cursor.execute("""
                        SELECT id, message_id, channel, user_id, user_display_name, message_content, timestamp
                        FROM messages 
                        WHERE channel = ? 
                        ORDER BY timestamp DESC 
                        LIMIT ?
                    """, (channel, limit))
                    
                elif self.db_type == 'mysql':
                    cursor.execute("""
                        SELECT id, message_id, channel, user_id, user_display_name, message_content, timestamp
                        FROM messages 
                        WHERE channel = %s 
                        ORDER BY timestamp DESC 
                        LIMIT %s
                    """, (channel, limit))
                
                rows = cursor.fetchall()
                messages = [Message.from_db_row(row) for row in rows]
                
                # Return in chronological order (oldest first)
                return list(reversed(messages))
                
        except Exception as e:
            logger.error(f"Failed to retrieve messages for {channel}: {e}")
            return []
    
    async def delete_message_by_id(self, message_id: str) -> bool:
        """
        Delete a specific message by ID (CLEARMSG event).
        
        Args:
            message_id: Unique message ID to delete
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            async with self.get_connection() as conn:
                cursor = conn.cursor()
                
                if self.db_type == 'sqlite':
                    cursor.execute("DELETE FROM messages WHERE message_id = ?", (message_id,))
                    conn.commit()
                elif self.db_type == 'mysql':
                    cursor.execute("DELETE FROM messages WHERE message_id = %s", (message_id,))
                
                return True
                
        except Exception as e:
            logger.error(f"Failed to delete message {message_id}: {e}")
            return False
    
    async def delete_user_messages(self, channel: str, user_id: str) -> bool:
        """
        Delete all messages from a user in a channel (CLEARCHAT user event).
        
        Args:
            channel: Channel name
            user_id: User ID whose messages to delete
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            async with self.get_connection() as conn:
                cursor = conn.cursor()
                
                if self.db_type == 'sqlite':
                    cursor.execute("DELETE FROM messages WHERE channel = ? AND user_id = ?", (channel, user_id))
                    conn.commit()
                elif self.db_type == 'mysql':
                    cursor.execute("DELETE FROM messages WHERE channel = %s AND user_id = %s", (channel, user_id))
                
                return True
                
        except Exception as e:
            logger.error(f"Failed to delete messages for user {user_id} in {channel}: {e}")
            return False
    
    async def clear_channel_messages(self, channel: str) -> bool:
        """
        Clear all messages in a channel (CLEARCHAT all event).
        
        Args:
            channel: Channel name
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            async with self.get_connection() as conn:
                cursor = conn.cursor()
                
                if self.db_type == 'sqlite':
                    cursor.execute("DELETE FROM messages WHERE channel = ?", (channel,))
                    conn.commit()
                elif self.db_type == 'mysql':
                    cursor.execute("DELETE FROM messages WHERE channel = %s", (channel,))
                
                return True
                
        except Exception as e:
            logger.error(f"Failed to clear messages in {channel}: {e}")
            return False
    
    async def cleanup_old_messages(self, channel: str, retention_days: int = 7) -> bool:
        """
        Clean up old messages based on retention policy.
        
        Args:
            channel: Channel name
            retention_days: Number of days to retain messages
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            cutoff_date = datetime.now() - timedelta(days=retention_days)
            
            async with self.get_connection() as conn:
                cursor = conn.cursor()
                
                if self.db_type == 'sqlite':
                    cursor.execute("DELETE FROM messages WHERE channel = ? AND timestamp < ?", (channel, cutoff_date))
                    conn.commit()
                elif self.db_type == 'mysql':
                    cursor.execute("DELETE FROM messages WHERE channel = %s AND timestamp < %s", (channel, cutoff_date))
                
                return True
                
        except Exception as e:
            logger.error(f"Failed to cleanup old messages in {channel}: {e}")
            return False
    
    async def count_recent_messages(self, channel: str, hours: int = 24) -> int:
        """
        Count recent messages in a channel.
        
        Args:
            channel: Channel name
            hours: Number of hours to look back
            
        Returns:
            int: Number of messages
        """
        try:
            cutoff_time = datetime.now() - timedelta(hours=hours)
            
            async with self.get_connection() as conn:
                cursor = conn.cursor()
                
                if self.db_type == 'sqlite':
                    cursor.execute("SELECT COUNT(*) FROM messages WHERE channel = ? AND timestamp > ?", (channel, cutoff_time))
                elif self.db_type == 'mysql':
                    cursor.execute("SELECT COUNT(*) FROM messages WHERE channel = %s AND timestamp > %s", (channel, cutoff_time))
                
                result = cursor.fetchone()
                return result[0] if result else 0
                
        except Exception as e:
            logger.error(f"Failed to count messages in {channel}: {e}")
            return 0
    
    async def execute(self, query: str, params: tuple = ()) -> Any:
        """
        Execute a single query with parameters.
        
        Args:
            query: SQL query string
            params: Query parameters
            
        Returns:
            Query result
        """
        try:
            async with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(query, params)
                
                if self.db_type == 'sqlite':
                    conn.commit()
                
                return cursor
                
        except Exception as e:
            logger.error(f"Failed to execute query: {e}")
            raise
    
    async def execute_many(self, query: str, params_list: List[tuple]) -> bool:
        """
        Execute a query with multiple parameter sets (batch insert).
        
        Args:
            query: SQL query string
            params_list: List of parameter tuples
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            async with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.executemany(query, params_list)
                
                if self.db_type == 'sqlite':
                    conn.commit()
                
                return True
                
        except Exception as e:
            logger.error(f"Failed to execute batch query: {e}")
            return False
    
    async def fetch_all(self, query: str, params: tuple = ()) -> List[Dict[str, Any]]:
        """
        Fetch all results from a query.
        
        Args:
            query: SQL query string
            params: Query parameters
            
        Returns:
            List of result dictionaries
        """
        try:
            async with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(query, params)
                
                # Get column names
                if self.db_type == 'sqlite':
                    columns = [description[0] for description in cursor.description]
                    rows = cursor.fetchall()
                    return [dict(zip(columns, row)) for row in rows]
                elif self.db_type == 'mysql':
                    columns = [description[0] for description in cursor.description]
                    rows = cursor.fetchall()
                    return [dict(zip(columns, row)) for row in rows]
                
        except Exception as e:
            logger.error(f"Failed to fetch query results: {e}")
            return []


def create_database_manager(config: Dict[str, str]) -> DatabaseManager:
    """
    Create appropriate database manager based on configuration.
    
    Args:
        config: Configuration dictionary with database settings
        
    Returns:
        DatabaseManager instance
    """
    db_type = config.get('DATABASE_TYPE', 'sqlite').lower()
    
    if db_type == 'mysql':
        return DatabaseManager(
            db_type='mysql',
            host=config['MYSQL_HOST'],
            port=int(config.get('MYSQL_PORT', 3306)),
            user=config['MYSQL_USER'],
            password=config['MYSQL_PASSWORD'],
            database=config['MYSQL_DATABASE']
        )
    else:  # Default to SQLite
        return DatabaseManager(
            db_type='sqlite',
            database_url=config.get('DATABASE_URL', './chatbot.db')
        )


class ChannelConfigManager:
    """Manages per-channel configuration with database persistence."""
    
    def __init__(self, db_manager: DatabaseManager):
        """
        Initialize ChannelConfigManager.
        
        Args:
            db_manager: DatabaseManager instance
        """
        self.db_manager = db_manager
        self._config_cache: Dict[str, ChannelConfig] = {}
    
    async def get_config(self, channel: str) -> ChannelConfig:
        """
        Get channel configuration, creating default if not exists.
        
        Args:
            channel: Channel name
            
        Returns:
            ChannelConfig object
        """
        # Check cache first
        if channel in self._config_cache:
            return self._config_cache[channel]
        
        try:
            async with self.db_manager.get_connection() as conn:
                cursor = conn.cursor()
                
                if self.db_manager.db_type == 'sqlite':
                    cursor.execute("SELECT * FROM channel_config WHERE channel = ?", (channel,))
                elif self.db_manager.db_type == 'mysql':
                    cursor.execute("SELECT * FROM channel_config WHERE channel = %s", (channel,))
                
                row = cursor.fetchone()
                
                if row:
                    config = ChannelConfig.from_db_row(row)
                else:
                    # Create default configuration
                    config = ChannelConfig(channel=channel)
                    await self._create_default_config(config)
                
                # Cache the configuration
                self._config_cache[channel] = config
                return config
                
        except Exception as e:
            logger.error(f"Failed to get config for {channel}: {e}")
            # Return default config on error
            return ChannelConfig(channel=channel)
    
    async def _create_default_config(self, config: ChannelConfig) -> bool:
        """Create default configuration in database."""
        try:
            async with self.db_manager.get_connection() as conn:
                cursor = conn.cursor()
                
                if self.db_manager.db_type == 'sqlite':
                    cursor.execute("""
                        INSERT OR IGNORE INTO channel_config 
                        (channel, message_threshold, spontaneous_cooldown, response_cooldown, context_limit, message_count)
                        VALUES (?, ?, ?, ?, ?, ?)
                    """, (
                        config.channel,
                        config.message_threshold,
                        config.spontaneous_cooldown,
                        config.response_cooldown,
                        config.context_limit,
                        config.message_count
                    ))
                    conn.commit()
                    
                elif self.db_manager.db_type == 'mysql':
                    cursor.execute("""
                        INSERT IGNORE INTO channel_config 
                        (channel, message_threshold, spontaneous_cooldown, response_cooldown, context_limit, message_count)
                        VALUES (%s, %s, %s, %s, %s, %s)
                    """, (
                        config.channel,
                        config.message_threshold,
                        config.spontaneous_cooldown,
                        config.response_cooldown,
                        config.context_limit,
                        config.message_count
                    ))
                
                return True
                
        except Exception as e:
            logger.error(f"Failed to create default config for {config.channel}: {e}")
            return False
    
    async def update_config(self, channel: str, key: str, value: Any) -> bool:
        """
        Update a specific configuration setting.
        
        Args:
            channel: Channel name
            key: Configuration key to update
            value: New value
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            # Validate the setting
            if not self._validate_setting(key, value):
                logger.warning(f"Invalid setting value: {key}={value}")
                return False
            
            async with self.db_manager.get_connection() as conn:
                cursor = conn.cursor()
                
                if self.db_manager.db_type == 'sqlite':
                    cursor.execute(f"""
                        UPDATE channel_config 
                        SET {key} = ?, updated_at = CURRENT_TIMESTAMP 
                        WHERE channel = ?
                    """, (value, channel))
                    conn.commit()
                    
                elif self.db_manager.db_type == 'mysql':
                    cursor.execute(f"""
                        UPDATE channel_config 
                        SET {key} = %s, updated_at = CURRENT_TIMESTAMP 
                        WHERE channel = %s
                    """, (value, channel))
                
                # Update cache
                if channel in self._config_cache:
                    setattr(self._config_cache[channel], key, value)
                    self._config_cache[channel].updated_at = datetime.now()
                
                return True
                
        except Exception as e:
            logger.error(f"Failed to update config {key}={value} for {channel}: {e}")
            return False
    
    def _validate_setting(self, key: str, value: Any) -> bool:
        """Validate configuration setting value."""
        validators = {
            'message_threshold': lambda v: isinstance(v, int) and 1 <= v <= 1000,
            'spontaneous_cooldown': lambda v: isinstance(v, int) and 0 <= v <= 3600,
            'response_cooldown': lambda v: isinstance(v, int) and 0 <= v <= 3600,
            'context_limit': lambda v: isinstance(v, int) and 10 <= v <= 1000,
            'ollama_model': lambda v: isinstance(v, (str, type(None))),
            'message_count': lambda v: isinstance(v, int) and v >= 0
        }
        
        validator = validators.get(key)
        return validator(value) if validator else False
    
    async def increment_message_count(self, channel: str) -> int:
        """
        Increment message count for a channel.
        
        Args:
            channel: Channel name
            
        Returns:
            int: New message count
        """
        try:
            async with self.db_manager.get_connection() as conn:
                cursor = conn.cursor()
                
                if self.db_manager.db_type == 'sqlite':
                    cursor.execute("""
                        UPDATE channel_config 
                        SET message_count = message_count + 1 
                        WHERE channel = ?
                    """, (channel,))
                    conn.commit()
                    
                    # Get the new count
                    cursor.execute("SELECT message_count FROM channel_config WHERE channel = ?", (channel,))
                    
                elif self.db_manager.db_type == 'mysql':
                    cursor.execute("""
                        UPDATE channel_config 
                        SET message_count = message_count + 1 
                        WHERE channel = %s
                    """, (channel,))
                    
                    # Get the new count
                    cursor.execute("SELECT message_count FROM channel_config WHERE channel = %s", (channel,))
                
                result = cursor.fetchone()
                new_count = result[0] if result else 0
                
                # Update cache
                if channel in self._config_cache:
                    self._config_cache[channel].message_count = new_count
                
                return new_count
                
        except Exception as e:
            logger.error(f"Failed to increment message count for {channel}: {e}")
            return 0
    
    async def reset_message_count(self, channel: str) -> bool:
        """
        Reset message count for a channel.
        
        Args:
            channel: Channel name
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            async with self.db_manager.get_connection() as conn:
                cursor = conn.cursor()
                
                if self.db_manager.db_type == 'sqlite':
                    cursor.execute("UPDATE channel_config SET message_count = 0 WHERE channel = ?", (channel,))
                    conn.commit()
                elif self.db_manager.db_type == 'mysql':
                    cursor.execute("UPDATE channel_config SET message_count = 0 WHERE channel = %s", (channel,))
                
                # Update cache
                if channel in self._config_cache:
                    self._config_cache[channel].message_count = 0
                
                return True
                
        except Exception as e:
            logger.error(f"Failed to reset message count for {channel}: {e}")
            return False
    
    async def update_spontaneous_timestamp(self, channel: str) -> bool:
        """
        Update the last spontaneous message timestamp.
        
        Args:
            channel: Channel name
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            now = datetime.now()
            
            async with self.db_manager.get_connection() as conn:
                cursor = conn.cursor()
                
                if self.db_manager.db_type == 'sqlite':
                    cursor.execute("""
                        UPDATE channel_config 
                        SET last_spontaneous_message = ? 
                        WHERE channel = ?
                    """, (now, channel))
                    conn.commit()
                elif self.db_manager.db_type == 'mysql':
                    cursor.execute("""
                        UPDATE channel_config 
                        SET last_spontaneous_message = %s 
                        WHERE channel = %s
                    """, (now, channel))
                
                # Update cache
                if channel in self._config_cache:
                    self._config_cache[channel].last_spontaneous_message = now
                
                return True
                
        except Exception as e:
            logger.error(f"Failed to update spontaneous timestamp for {channel}: {e}")
            return False
    
    async def can_generate_spontaneous(self, channel: str) -> bool:
        """
        Check if bot can generate a spontaneous message.
        
        Args:
            channel: Channel name
            
        Returns:
            bool: True if can generate, False otherwise
        """
        try:
            config = await self.get_config(channel)
            
            # Check message count threshold
            if config.message_count < config.message_threshold:
                return False
            
            # Check spontaneous cooldown
            if config.last_spontaneous_message:
                time_since = datetime.now() - config.last_spontaneous_message
                if time_since.total_seconds() < config.spontaneous_cooldown:
                    return False
            
            # Check adequate context
            available_messages = await self.db_manager.count_recent_messages(channel)
            if available_messages < 10:
                return False
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to check spontaneous generation for {channel}: {e}")
            return False
    
    async def can_respond_to_user(self, channel: str, user_id: str) -> bool:
        """
        Check if bot can respond to a user's mention.
        
        Args:
            channel: Channel name
            user_id: User ID
            
        Returns:
            bool: True if can respond, False otherwise
        """
        try:
            config = await self.get_config(channel)
            
            # Get user's last response time
            last_response = await self._get_user_last_response(channel, user_id)
            
            if last_response:
                time_since = datetime.now() - last_response
                if time_since.total_seconds() < config.response_cooldown:
                    return False
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to check user response cooldown for {user_id} in {channel}: {e}")
            return False
    
    async def _get_user_last_response(self, channel: str, user_id: str) -> Optional[datetime]:
        """Get user's last response time."""
        try:
            async with self.db_manager.get_connection() as conn:
                cursor = conn.cursor()
                
                if self.db_manager.db_type == 'sqlite':
                    cursor.execute("""
                        SELECT last_response_time FROM user_response_cooldowns 
                        WHERE channel = ? AND user_id = ?
                    """, (channel, user_id))
                elif self.db_manager.db_type == 'mysql':
                    cursor.execute("""
                        SELECT last_response_time FROM user_response_cooldowns 
                        WHERE channel = %s AND user_id = %s
                    """, (channel, user_id))
                
                result = cursor.fetchone()
                if result:
                    return result[0] if isinstance(result[0], datetime) else datetime.fromisoformat(str(result[0]))
                return None
                
        except Exception as e:
            logger.error(f"Failed to get user last response for {user_id} in {channel}: {e}")
            return None
    
    async def update_user_response_timestamp(self, channel: str, user_id: str) -> bool:
        """
        Update user's response timestamp.
        
        Args:
            channel: Channel name
            user_id: User ID
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            now = datetime.now()
            
            async with self.db_manager.get_connection() as conn:
                cursor = conn.cursor()
                
                if self.db_manager.db_type == 'sqlite':
                    cursor.execute("""
                        INSERT OR REPLACE INTO user_response_cooldowns 
                        (channel, user_id, last_response_time) 
                        VALUES (?, ?, ?)
                    """, (channel, user_id, now))
                    conn.commit()
                elif self.db_manager.db_type == 'mysql':
                    cursor.execute("""
                        INSERT INTO user_response_cooldowns 
                        (channel, user_id, last_response_time) 
                        VALUES (%s, %s, %s)
                        ON DUPLICATE KEY UPDATE last_response_time = %s
                    """, (channel, user_id, now, now))
                
                return True
                
        except Exception as e:
            logger.error(f"Failed to update user response timestamp for {user_id} in {channel}: {e}")
            return False
    
    async def load_persistent_state(self, channel: str) -> None:
        """
        Load persistent state for a channel on startup.
        
        Args:
            channel: Channel name
        """
        try:
            # Load configuration to populate cache
            await self.get_config(channel)
            logger.info(f"Loaded persistent state for {channel}")
            
        except Exception as e:
            logger.error(f"Failed to load persistent state for {channel}: {e}")
    
    async def save_persistent_state(self, channel: str) -> None:
        """
        Save persistent state for a channel.
        
        Args:
            channel: Channel name
        """
        try:
            # State is automatically saved via database operations
            # This method exists for interface completeness
            logger.debug(f"Persistent state saved for {channel}")
            
        except Exception as e:
            logger.error(f"Failed to save persistent state for {channel}: {e}")
    
    async def update_user_response_timestamp(self, channel: str, user_id: str) -> bool:
        """
        Update user's response timestamp for rate limiting.
        
        Args:
            channel: Channel name
            user_id: User ID
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            now = datetime.now()
            
            async with self.db_manager.get_connection() as conn:
                cursor = conn.cursor()
                
                if self.db_manager.db_type == 'sqlite':
                    cursor.execute("""
                        INSERT OR REPLACE INTO user_response_cooldowns 
                        (channel, user_id, last_response_time) 
                        VALUES (?, ?, ?)
                    """, (channel, user_id, now))
                    conn.commit()
                    
                elif self.db_manager.db_type == 'mysql':
                    cursor.execute("""
                        INSERT INTO user_response_cooldowns 
                        (channel, user_id, last_response_time) 
                        VALUES (%s, %s, %s)
                        ON DUPLICATE KEY UPDATE last_response_time = %s
                    """, (channel, user_id, now, now))
                
                return True
                
        except Exception as e:
            logger.error(f"Failed to update user response timestamp for {user_id} in {channel}: {e}")
            return False
    
    async def get_user_last_response(self, channel: str, user_id: str) -> Optional[datetime]:
        """
        Get user's last response time.
        
        Args:
            channel: Channel name
            user_id: User ID
            
        Returns:
            Last response datetime or None if never responded
        """
        try:
            async with self.db_manager.get_connection() as conn:
                cursor = conn.cursor()
                
                if self.db_manager.db_type == 'sqlite':
                    cursor.execute("""
                        SELECT last_response_time FROM user_response_cooldowns 
                        WHERE channel = ? AND user_id = ?
                    """, (channel, user_id))
                elif self.db_manager.db_type == 'mysql':
                    cursor.execute("""
                        SELECT last_response_time FROM user_response_cooldowns 
                        WHERE channel = %s AND user_id = %s
                    """, (channel, user_id))
                
                result = cursor.fetchone()
                if result:
                    return result[0] if isinstance(result[0], datetime) else datetime.fromisoformat(str(result[0]))
                return None
                
        except Exception as e:
            logger.error(f"Failed to get user last response for {user_id} in {channel}: {e}")
            return None
    
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
                
                logger.info(f"Cleaned up {deleted_count} old user cooldown records (older than {days} days)")
                return True
                
        except Exception as e:
            logger.error(f"Failed to cleanup old user cooldowns: {e}")
            return False


class AuthTokenManager:
    """Manages OAuth token storage and retrieval operations."""
    
    def __init__(self, db_manager: DatabaseManager):
        """
        Initialize AuthTokenManager.
        
        Args:
            db_manager: DatabaseManager instance
        """
        self.db_manager = db_manager
    
    async def store_auth_tokens(self, auth_token: AuthToken) -> bool:
        """
        Store authentication tokens in database.
        
        Args:
            auth_token: AuthToken object to store
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            async with self.db_manager.get_connection() as conn:
                cursor = conn.cursor()
                
                # First, clear any existing tokens (only one set of tokens at a time)
                if self.db_manager.db_type == 'sqlite':
                    cursor.execute("DELETE FROM auth_tokens")
                    cursor.execute("""
                        INSERT INTO auth_tokens 
                        (access_token, refresh_token, expires_at, bot_username, created_at)
                        VALUES (?, ?, ?, ?, ?)
                    """, (
                        auth_token.access_token,
                        auth_token.refresh_token,
                        auth_token.expires_at,
                        auth_token.bot_username,
                        auth_token.created_at
                    ))
                    conn.commit()
                    
                elif self.db_manager.db_type == 'mysql':
                    cursor.execute("DELETE FROM auth_tokens")
                    cursor.execute("""
                        INSERT INTO auth_tokens 
                        (access_token, refresh_token, expires_at, bot_username, created_at)
                        VALUES (%s, %s, %s, %s, %s)
                    """, (
                        auth_token.access_token,
                        auth_token.refresh_token,
                        auth_token.expires_at,
                        auth_token.bot_username,
                        auth_token.created_at
                    ))
                
                logger.info("Authentication tokens stored successfully")
                return True
                
        except Exception as e:
            logger.error(f"Failed to store auth tokens: {e}")
            return False
    
    async def get_auth_tokens(self) -> Optional[AuthToken]:
        """
        Retrieve stored authentication tokens.
        
        Returns:
            Optional[AuthToken]: AuthToken object or None if not found
        """
        try:
            async with self.db_manager.get_connection() as conn:
                cursor = conn.cursor()
                
                if self.db_manager.db_type == 'sqlite':
                    cursor.execute("""
                        SELECT id, access_token, refresh_token, expires_at, bot_username, created_at
                        FROM auth_tokens 
                        ORDER BY created_at DESC 
                        LIMIT 1
                    """)
                elif self.db_manager.db_type == 'mysql':
                    cursor.execute("""
                        SELECT id, access_token, refresh_token, expires_at, bot_username, created_at
                        FROM auth_tokens 
                        ORDER BY created_at DESC 
                        LIMIT 1
                    """)
                
                row = cursor.fetchone()
                if row:
                    return AuthToken.from_db_row(row)
                return None
                
        except Exception as e:
            logger.error(f"Failed to retrieve auth tokens: {e}")
            return None
    
    async def update_auth_tokens(self, auth_token: AuthToken) -> bool:
        """
        Update existing authentication tokens.
        
        Args:
            auth_token: Updated AuthToken object
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            async with self.db_manager.get_connection() as conn:
                cursor = conn.cursor()
                
                if self.db_manager.db_type == 'sqlite':
                    cursor.execute("""
                        UPDATE auth_tokens 
                        SET access_token = ?, refresh_token = ?, expires_at = ?, 
                            bot_username = ?, created_at = ?
                        WHERE id = ?
                    """, (
                        auth_token.access_token,
                        auth_token.refresh_token,
                        auth_token.expires_at,
                        auth_token.bot_username,
                        datetime.now(),
                        auth_token.id
                    ))
                    conn.commit()
                    
                elif self.db_manager.db_type == 'mysql':
                    cursor.execute("""
                        UPDATE auth_tokens 
                        SET access_token = %s, refresh_token = %s, expires_at = %s, 
                            bot_username = %s, created_at = %s
                        WHERE id = %s
                    """, (
                        auth_token.access_token,
                        auth_token.refresh_token,
                        auth_token.expires_at,
                        auth_token.bot_username,
                        datetime.now(),
                        auth_token.id
                    ))
                
                logger.info("Authentication tokens updated successfully")
                return True
                
        except Exception as e:
            logger.error(f"Failed to update auth tokens: {e}")
            return False
    
    async def delete_auth_tokens(self) -> bool:
        """
        Delete all stored authentication tokens.
        
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            async with self.db_manager.get_connection() as conn:
                cursor = conn.cursor()
                
                if self.db_manager.db_type == 'sqlite':
                    cursor.execute("DELETE FROM auth_tokens")
                    conn.commit()
                elif self.db_manager.db_type == 'mysql':
                    cursor.execute("DELETE FROM auth_tokens")
                
                logger.info("Authentication tokens deleted successfully")
                return True
                
        except Exception as e:
            logger.error(f"Failed to delete auth tokens: {e}")
            return False
    
    async def load_persistent_state(self, channel: str) -> bool:
        """
        Load persistent state for a channel on startup.
        
        Args:
            channel: Channel name
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            # This will load the config into cache
            config = await self.get_config(channel)
            logger.info(f"Loaded persistent state for {channel}: count={config.message_count}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to load persistent state for {channel}: {e}")
            return False
    
    async def save_persistent_state(self, channel: str) -> bool:
        """
        Save persistent state for a channel on shutdown.
        
        Args:
            channel: Channel name
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            # State is automatically saved to database on updates
            # This method is for any additional cleanup if needed
            logger.info(f"Persistent state saved for {channel}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to save persistent state for {channel}: {e}")
            return False
    
    def clear_cache(self, channel: Optional[str] = None):
        """
        Clear configuration cache.
        
        Args:
            channel: Specific channel to clear, or None for all
        """
        if channel:
            self._config_cache.pop(channel, None)
        else:
            self._config_cache.clear()


class MetricsManager:
    """Manages bot performance metrics and monitoring."""
    
    def __init__(self, db_manager: DatabaseManager):
        """
        Initialize MetricsManager.
        
        Args:
            db_manager: DatabaseManager instance
        """
        self.db_manager = db_manager
    
    async def record_response_time(self, channel: str, duration: float) -> bool:
        """
        Record response time metric.
        
        Args:
            channel: Channel name
            duration: Response time in seconds
            
        Returns:
            bool: True if successful, False otherwise
        """
        return await self._record_metric(channel, 'response_time', duration)
    
    async def record_success(self, channel: str) -> bool:
        """
        Record successful operation.
        
        Args:
            channel: Channel name
            
        Returns:
            bool: True if successful, False otherwise
        """
        return await self._record_metric(channel, 'success_count', 1.0)
    
    async def record_error(self, channel: str, error_type: str) -> bool:
        """
        Record error occurrence.
        
        Args:
            channel: Channel name
            error_type: Type of error
            
        Returns:
            bool: True if successful, False otherwise
        """
        return await self._record_metric(channel, f'error_{error_type}', 1.0)
    
    async def _record_metric(self, channel: str, metric_type: str, value: float) -> bool:
        """Record a metric in the database."""
        try:
            async with self.db_manager.get_connection() as conn:
                cursor = conn.cursor()
                
                if self.db_manager.db_type == 'sqlite':
                    cursor.execute("""
                        INSERT INTO bot_metrics (channel, metric_type, metric_value)
                        VALUES (?, ?, ?)
                    """, (channel, metric_type, value))
                    conn.commit()
                elif self.db_manager.db_type == 'mysql':
                    cursor.execute("""
                        INSERT INTO bot_metrics (channel, metric_type, metric_value)
                        VALUES (%s, %s, %s)
                    """, (channel, metric_type, value))
                
                return True
                
        except Exception as e:
            logger.error(f"Failed to record metric {metric_type}={value} for {channel}: {e}")
            return False
    
    async def get_performance_stats(self, channel: str, hours: int = 24) -> Dict[str, Any]:
        """
        Get performance statistics for a channel.
        
        Args:
            channel: Channel name
            hours: Number of hours to look back
            
        Returns:
            Dict with performance statistics
        """
        try:
            cutoff_time = datetime.now() - timedelta(hours=hours)
            
            async with self.db_manager.get_connection() as conn:
                cursor = conn.cursor()
                
                if self.db_manager.db_type == 'sqlite':
                    cursor.execute("""
                        SELECT metric_type, AVG(metric_value), COUNT(*), MAX(metric_value), MIN(metric_value)
                        FROM bot_metrics 
                        WHERE channel = ? AND timestamp > ?
                        GROUP BY metric_type
                    """, (channel, cutoff_time))
                elif self.db_manager.db_type == 'mysql':
                    cursor.execute("""
                        SELECT metric_type, AVG(metric_value), COUNT(*), MAX(metric_value), MIN(metric_value)
                        FROM bot_metrics 
                        WHERE channel = %s AND timestamp > %s
                        GROUP BY metric_type
                    """, (channel, cutoff_time))
                
                rows = cursor.fetchall()
                stats = {}
                
                for row in rows:
                    metric_type, avg_value, count, max_value, min_value = row
                    stats[metric_type] = {
                        'average': float(avg_value),
                        'count': int(count),
                        'maximum': float(max_value),
                        'minimum': float(min_value)
                    }
                
                return stats
                
        except Exception as e:
            logger.error(f"Failed to get performance stats for {channel}: {e}")
            return {}
    
    async def cleanup_old_metrics(self, retention_days: int = 7) -> bool:
        """
        Clean up old metrics data.
        
        Args:
            retention_days: Number of days to retain metrics
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            cutoff_date = datetime.now() - timedelta(days=retention_days)
            
            async with self.db_manager.get_connection() as conn:
                cursor = conn.cursor()
                
                if self.db_manager.db_type == 'sqlite':
                    cursor.execute("DELETE FROM bot_metrics WHERE timestamp < ?", (cutoff_date,))
                    conn.commit()
                elif self.db_manager.db_type == 'mysql':
                    cursor.execute("DELETE FROM bot_metrics WHERE timestamp < %s", (cutoff_date,))
                
                return True
                
        except Exception as e:
            logger.error(f"Failed to cleanup old metrics: {e}")
            return False