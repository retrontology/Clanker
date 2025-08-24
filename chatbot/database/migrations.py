"""
Database schema management and migrations.

This module handles database initialization and schema creation
for both SQLite and MySQL databases.
"""

import sqlite3
import mysql.connector
from typing import Dict, Any, Optional
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


class DatabaseMigrations:
    """Handles database schema creation and migrations."""
    
    def __init__(self, db_type: str, connection_params: Dict[str, Any]):
        """
        Initialize database migrations.
        
        Args:
            db_type: Either 'sqlite' or 'mysql'
            connection_params: Database connection parameters
        """
        self.db_type = db_type.lower()
        self.connection_params = connection_params
        
    async def initialize_database(self) -> bool:
        """
        Initialize database and create all required tables.
        
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            if self.db_type == 'sqlite':
                return await self._initialize_sqlite()
            elif self.db_type == 'mysql':
                return await self._initialize_mysql()
            else:
                logger.error(f"Unsupported database type: {self.db_type}")
                return False
        except Exception as e:
            logger.error(f"Database initialization failed: {e}")
            return False
    
    async def _initialize_sqlite(self) -> bool:
        """Initialize SQLite database and create schema."""
        database_path = self.connection_params.get('database_url', './chatbot.db')
        
        # Ensure directory exists
        Path(database_path).parent.mkdir(parents=True, exist_ok=True)
        
        conn = sqlite3.connect(database_path)
        try:
            cursor = conn.cursor()
            
            # Create all tables
            for table_sql in self._get_sqlite_schema():
                cursor.execute(table_sql)
            
            # Create indexes
            for index_sql in self._get_sqlite_indexes():
                cursor.execute(index_sql)
            
            conn.commit()
            logger.info(f"SQLite database initialized at {database_path}")
            return True
            
        except Exception as e:
            logger.error(f"SQLite initialization failed: {e}")
            conn.rollback()
            return False
        finally:
            conn.close()
    
    async def _initialize_mysql(self) -> bool:
        """Initialize MySQL database and create schema."""
        try:
            # Connect to MySQL server
            conn = mysql.connector.connect(
                host=self.connection_params['host'],
                port=self.connection_params.get('port', 3306),
                user=self.connection_params['user'],
                password=self.connection_params['password']
            )
            
            cursor = conn.cursor()
            
            # Create database if it doesn't exist
            database_name = self.connection_params['database']
            cursor.execute(f"CREATE DATABASE IF NOT EXISTS {database_name}")
            cursor.execute(f"USE {database_name}")
            
            # Create all tables
            for table_sql in self._get_mysql_schema():
                cursor.execute(table_sql)
            
            # Create indexes
            for index_sql in self._get_mysql_indexes():
                cursor.execute(index_sql)
            
            conn.commit()
            logger.info(f"MySQL database initialized: {database_name}")
            return True
            
        except Exception as e:
            logger.error(f"MySQL initialization failed: {e}")
            if 'conn' in locals():
                conn.rollback()
            return False
        finally:
            if 'conn' in locals():
                conn.close()
    
    def _get_sqlite_schema(self) -> list[str]:
        """Get SQLite table creation statements."""
        return [
            # Core message storage
            """
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                message_id TEXT UNIQUE NOT NULL,
                channel TEXT NOT NULL,
                user_id TEXT NOT NULL,
                user_display_name TEXT NOT NULL,
                message_content TEXT NOT NULL,
                timestamp DATETIME NOT NULL
            )
            """,
            
            # Channel-specific configuration
            """
            CREATE TABLE IF NOT EXISTS channel_config (
                channel TEXT PRIMARY KEY,
                message_threshold INTEGER DEFAULT 30,
                spontaneous_cooldown INTEGER DEFAULT 300,
                response_cooldown INTEGER DEFAULT 60,
                context_limit INTEGER DEFAULT 200,
                ollama_model TEXT,
                message_count INTEGER DEFAULT 0,
                last_spontaneous_message DATETIME,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            """,
            
            # Per-user response cooldowns (channel-specific)
            """
            CREATE TABLE IF NOT EXISTS user_response_cooldowns (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                channel TEXT NOT NULL,
                user_id TEXT NOT NULL,
                last_response_time DATETIME NOT NULL,
                UNIQUE(channel, user_id)
            )
            """,
            
            # Performance and monitoring metrics
            """
            CREATE TABLE IF NOT EXISTS bot_metrics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                channel TEXT NOT NULL,
                metric_type TEXT NOT NULL,
                metric_value REAL NOT NULL,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            """,
            
            # OAuth token storage
            """
            CREATE TABLE IF NOT EXISTS auth_tokens (
                id INTEGER PRIMARY KEY,
                access_token TEXT NOT NULL,
                refresh_token TEXT,
                expires_at DATETIME,
                bot_username TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            """
        ]
    
    def _get_mysql_schema(self) -> list[str]:
        """Get MySQL table creation statements."""
        return [
            # Core message storage
            """
            CREATE TABLE IF NOT EXISTS messages (
                id INT AUTO_INCREMENT PRIMARY KEY,
                message_id VARCHAR(255) UNIQUE NOT NULL,
                channel VARCHAR(255) NOT NULL,
                user_id VARCHAR(255) NOT NULL,
                user_display_name VARCHAR(255) NOT NULL,
                message_content TEXT NOT NULL,
                timestamp DATETIME NOT NULL
            )
            """,
            
            # Channel-specific configuration
            """
            CREATE TABLE IF NOT EXISTS channel_config (
                channel VARCHAR(255) PRIMARY KEY,
                message_threshold INT DEFAULT 30,
                spontaneous_cooldown INT DEFAULT 300,
                response_cooldown INT DEFAULT 60,
                context_limit INT DEFAULT 200,
                ollama_model VARCHAR(255),
                message_count INT DEFAULT 0,
                last_spontaneous_message DATETIME,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
            )
            """,
            
            # Per-user response cooldowns (channel-specific)
            """
            CREATE TABLE IF NOT EXISTS user_response_cooldowns (
                id INT AUTO_INCREMENT PRIMARY KEY,
                channel VARCHAR(255) NOT NULL,
                user_id VARCHAR(255) NOT NULL,
                last_response_time DATETIME NOT NULL,
                UNIQUE KEY unique_channel_user (channel, user_id)
            )
            """,
            
            # Performance and monitoring metrics
            """
            CREATE TABLE IF NOT EXISTS bot_metrics (
                id INT AUTO_INCREMENT PRIMARY KEY,
                channel VARCHAR(255) NOT NULL,
                metric_type VARCHAR(255) NOT NULL,
                metric_value DECIMAL(10,4) NOT NULL,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            """,
            
            # OAuth token storage
            """
            CREATE TABLE IF NOT EXISTS auth_tokens (
                id INT AUTO_INCREMENT PRIMARY KEY,
                access_token TEXT NOT NULL,
                refresh_token TEXT,
                expires_at DATETIME,
                bot_username VARCHAR(255),
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            """
        ]
    
    def _get_sqlite_indexes(self) -> list[str]:
        """Get SQLite index creation statements."""
        return [
            "CREATE INDEX IF NOT EXISTS idx_messages_channel_timestamp ON messages (channel, timestamp)",
            "CREATE INDEX IF NOT EXISTS idx_messages_message_id ON messages (message_id)",
            "CREATE INDEX IF NOT EXISTS idx_messages_user_id ON messages (user_id)",
            "CREATE INDEX IF NOT EXISTS idx_user_cooldowns_channel_user ON user_response_cooldowns (channel, user_id)",
            "CREATE INDEX IF NOT EXISTS idx_bot_metrics_channel_metric_time ON bot_metrics (channel, metric_type, timestamp)"
        ]
    
    def _get_mysql_indexes(self) -> list[str]:
        """Get MySQL index creation statements."""
        return [
            "CREATE INDEX idx_messages_channel_timestamp ON messages (channel, timestamp)",
            "CREATE INDEX idx_messages_message_id ON messages (message_id)",
            "CREATE INDEX idx_messages_user_id ON messages (user_id)",
            "CREATE INDEX idx_user_cooldowns_channel_user ON user_response_cooldowns (channel, user_id)",
            "CREATE INDEX idx_bot_metrics_channel_metric_time ON bot_metrics (channel, metric_type, timestamp)"
        ]