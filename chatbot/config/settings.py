"""
Global configuration management for the Twitch Ollama Chatbot.

This module handles loading and validation of environment variables
and global application settings.
"""

import os
from dataclasses import dataclass
from typing import List, Optional
from dotenv import load_dotenv


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