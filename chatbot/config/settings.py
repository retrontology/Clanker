"""
Global configuration management for the Twitch Ollama Chatbot.

This module handles loading and validation of environment variables
and global application settings.
"""

import os
import logging
from dataclasses import dataclass
from typing import List, Optional, Dict, Any
from dotenv import load_dotenv

logger = logging.getLogger(__name__)


@dataclass
class GlobalConfig:
    """Global configuration settings loaded from environment variables."""
    
    # Required fields (no defaults)
    database_type: str
    database_url: str
    ollama_url: str
    ollama_model: str
    ollama_timeout: int
    twitch_client_id: str
    twitch_client_secret: str
    channels: List[str]
    content_filter_enabled: bool
    blocked_words_file: str
    log_level: str
    log_format: str
    
    # Optional fields (with defaults)
    mysql_host: Optional[str] = None
    mysql_port: int = 3306
    mysql_user: Optional[str] = None
    mysql_password: Optional[str] = None
    mysql_database: Optional[str] = None


def load_global_config() -> GlobalConfig:
    """
    Load global configuration from environment variables.
    
    Returns:
        GlobalConfig: Loaded and validated configuration
        
    Raises:
        ValueError: If required environment variables are missing or invalid
    """
    # Load environment variables from .env file if present
    load_dotenv()
    
    # Database configuration
    database_type = os.getenv('DATABASE_TYPE', 'sqlite').lower()
    database_url = os.getenv('DATABASE_URL', './chatbot.db')
    
    # MySQL configuration (only required if using MySQL)
    mysql_host = os.getenv('MYSQL_HOST')
    mysql_port = int(os.getenv('MYSQL_PORT', '3306'))
    mysql_user = os.getenv('MYSQL_USER')
    mysql_password = os.getenv('MYSQL_PASSWORD')
    mysql_database = os.getenv('MYSQL_DATABASE')
    
    # Validate MySQL configuration if using MySQL
    if database_type == 'mysql':
        if not all([mysql_host, mysql_user, mysql_password, mysql_database]):
            raise ValueError(
                "MySQL configuration incomplete. Required: MYSQL_HOST, "
                "MYSQL_USER, MYSQL_PASSWORD, MYSQL_DATABASE"
            )
    
    # Ollama configuration
    ollama_url = os.getenv('OLLAMA_URL', 'http://localhost:11434')
    ollama_model = os.getenv('OLLAMA_MODEL')
    if not ollama_model:
        raise ValueError("OLLAMA_MODEL environment variable is required")
    
    ollama_timeout = int(os.getenv('OLLAMA_TIMEOUT', '30'))
    
    # Twitch configuration
    twitch_client_id = os.getenv('TWITCH_CLIENT_ID')
    twitch_client_secret = os.getenv('TWITCH_CLIENT_SECRET')
    
    if not twitch_client_id or not twitch_client_secret:
        raise ValueError(
            "Twitch configuration incomplete. Required: TWITCH_CLIENT_ID, "
            "TWITCH_CLIENT_SECRET"
        )
    
    # Parse channels list
    channels_str = os.getenv('TWITCH_CHANNELS', '')
    channels = [ch.strip() for ch in channels_str.split(',') if ch.strip()]
    
    if not channels:
        raise ValueError("At least one channel must be specified in TWITCH_CHANNELS")
    
    # Content filtering configuration
    content_filter_enabled = os.getenv('CONTENT_FILTER_ENABLED', 'true').lower() == 'true'
    blocked_words_file = os.getenv('BLOCKED_WORDS_FILE', './blocked_words.txt')
    
    # Logging configuration
    log_level = os.getenv('LOG_LEVEL', 'INFO').upper()
    log_format = os.getenv('LOG_FORMAT', 'console')  # 'console' or 'json'
    
    return GlobalConfig(
        database_type=database_type,
        database_url=database_url,
        mysql_host=mysql_host,
        mysql_port=mysql_port,
        mysql_user=mysql_user,
        mysql_password=mysql_password,
        mysql_database=mysql_database,
        ollama_url=ollama_url,
        ollama_model=ollama_model,
        ollama_timeout=ollama_timeout,
        twitch_client_id=twitch_client_id,
        twitch_client_secret=twitch_client_secret,
        channels=channels,
        content_filter_enabled=content_filter_enabled,
        blocked_words_file=blocked_words_file,
        log_level=log_level,
        log_format=log_format
    )


def validate_config(config: GlobalConfig) -> None:
    """
    Validate configuration values for consistency and correctness.
    
    Args:
        config: Configuration to validate
        
    Raises:
        ValueError: If configuration is invalid
    """
    # Validate log level
    valid_log_levels = ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']
    if config.log_level not in valid_log_levels:
        raise ValueError(f"Invalid log level: {config.log_level}")
    
    # Validate log format
    valid_log_formats = ['console', 'json']
    if config.log_format not in valid_log_formats:
        raise ValueError(f"Invalid log format: {config.log_format}")
    
    # Validate database type
    valid_db_types = ['sqlite', 'mysql']
    if config.database_type not in valid_db_types:
        raise ValueError(f"Invalid database type: {config.database_type}")
    
    # Validate timeout values
    if config.ollama_timeout <= 0:
        raise ValueError("Ollama timeout must be positive")
    
    if config.mysql_port <= 0 or config.mysql_port > 65535:
        raise ValueError("MySQL port must be between 1 and 65535")


class ConfigurationSystem:
    """
    Unified configuration system that manages both global and per-channel settings.
    
    Provides a single interface for accessing configuration values with proper
    fallback from channel-specific to global defaults.
    """
    
    def __init__(self, global_config: GlobalConfig, channel_config_manager):
        """
        Initialize configuration system.
        
        Args:
            global_config: Global configuration from environment variables
            channel_config_manager: ChannelConfigManager instance
        """
        self.global_config = global_config
        self.channel_config_manager = channel_config_manager
        
        logger.info("Configuration system initialized", extra={
            'database_type': global_config.database_type,
            'ollama_url': global_config.ollama_url,
            'default_model': global_config.ollama_model,
            'channels': len(global_config.channels)
        })
    
    async def get_effective_config(self, channel: str) -> Dict[str, Any]:
        """
        Get effective configuration for a channel (channel-specific + global fallbacks).
        
        Args:
            channel: Channel name
            
        Returns:
            Dictionary with effective configuration values
        """
        try:
            # Get channel-specific configuration
            channel_config = await self.channel_config_manager.get_config(channel)
            
            # Build effective configuration with fallbacks
            effective_config = {
                # Global settings (no channel override)
                'database_type': self.global_config.database_type,
                'database_url': self.global_config.database_url,
                'ollama_url': self.global_config.ollama_url,
                'ollama_timeout': self.global_config.ollama_timeout,
                'content_filter_enabled': self.global_config.content_filter_enabled,
                'blocked_words_file': self.global_config.blocked_words_file,
                'log_level': self.global_config.log_level,
                'log_format': self.global_config.log_format,
                
                # Channel-specific settings with global fallbacks
                'ollama_model': channel_config.ollama_model or self.global_config.ollama_model,
                'message_threshold': channel_config.message_threshold,
                'spontaneous_cooldown': channel_config.spontaneous_cooldown,
                'response_cooldown': channel_config.response_cooldown,
                'context_limit': channel_config.context_limit,
                
                # Channel state
                'message_count': channel_config.message_count,
                'last_spontaneous_message': channel_config.last_spontaneous_message,
            }
            
            return effective_config
            
        except Exception as e:
            logger.error(f"Failed to get effective config for {channel}: {e}")
            # Return global defaults on error
            return self._get_global_defaults()
    
    def _get_global_defaults(self) -> Dict[str, Any]:
        """Get global default configuration values."""
        return {
            'database_type': self.global_config.database_type,
            'database_url': self.global_config.database_url,
            'ollama_url': self.global_config.ollama_url,
            'ollama_timeout': self.global_config.ollama_timeout,
            'ollama_model': self.global_config.ollama_model,
            'content_filter_enabled': self.global_config.content_filter_enabled,
            'blocked_words_file': self.global_config.blocked_words_file,
            'log_level': self.global_config.log_level,
            'log_format': self.global_config.log_format,
            'message_threshold': 30,
            'spontaneous_cooldown': 300,
            'response_cooldown': 60,
            'context_limit': 200,
            'message_count': 0,
            'last_spontaneous_message': None,
        }
    
    async def initialize_channel_configs(self) -> bool:
        """
        Initialize configuration for all configured channels.
        
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            success_count = 0
            
            for channel in self.global_config.channels:
                try:
                    # This will create default config if it doesn't exist
                    config = await self.channel_config_manager.get_config(channel)
                    logger.info(f"Channel configuration loaded", extra={
                        'channel': channel,
                        'threshold': config.message_threshold,
                        'spontaneous_cooldown': config.spontaneous_cooldown,
                        'response_cooldown': config.response_cooldown,
                        'model': config.ollama_model or 'default'
                    })
                    success_count += 1
                    
                except Exception as e:
                    logger.error(f"Failed to initialize config for {channel}: {e}")
            
            logger.info(f"Channel configuration initialization complete", extra={
                'total_channels': len(self.global_config.channels),
                'successful': success_count,
                'failed': len(self.global_config.channels) - success_count
            })
            
            return success_count > 0
            
        except Exception as e:
            logger.error(f"Channel configuration initialization failed: {e}")
            return False
    
    async def load_persistent_state(self) -> bool:
        """
        Load persistent state for all channels during startup.
        
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            for channel in self.global_config.channels:
                try:
                    # Load channel configuration (includes persistent state)
                    config = await self.channel_config_manager.get_config(channel)
                    
                    logger.debug(f"Loaded persistent state for {channel}", extra={
                        'message_count': config.message_count,
                        'last_spontaneous': config.last_spontaneous_message.isoformat() if config.last_spontaneous_message else None
                    })
                    
                except Exception as e:
                    logger.warning(f"Failed to load persistent state for {channel}: {e}")
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to load persistent state: {e}")
            return False
    
    async def save_persistent_state(self) -> bool:
        """
        Save persistent state for all channels during shutdown.
        
        Note: State is automatically saved when updated, so this is mainly
        for ensuring consistency during shutdown.
        
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            # State is automatically persisted in database when updated
            # This method exists for consistency and future enhancements
            logger.info("Persistent state save completed (automatic persistence)")
            return True
            
        except Exception as e:
            logger.error(f"Failed to save persistent state: {e}")
            return False
    
    def get_global_config(self) -> GlobalConfig:
        """Get global configuration object."""
        return self.global_config
    
    async def get_channel_config_manager(self):
        """Get channel configuration manager."""
        return self.channel_config_manager