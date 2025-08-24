"""
Database models and schema definitions.

This module defines the database models for message storage,
configuration, and authentication.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Dict, Any
import json


@dataclass
class Message:
    """Represents a chat message stored in the database."""
    id: Optional[int]
    message_id: str
    channel: str
    user_id: str
    user_display_name: str
    message_content: str
    timestamp: datetime
    
    @classmethod
    def from_db_row(cls, row: tuple) -> 'Message':
        """Create Message instance from database row."""
        return cls(
            id=row[0],
            message_id=row[1],
            channel=row[2],
            user_id=row[3],
            user_display_name=row[4],
            message_content=row[5],
            timestamp=row[6] if isinstance(row[6], datetime) else datetime.fromisoformat(str(row[6]))
        )


@dataclass
class ChannelConfig:
    """Represents channel-specific configuration."""
    channel: str
    message_threshold: int = 30
    spontaneous_cooldown: int = 300  # 5 minutes default
    response_cooldown: int = 60      # 1 minute default
    context_limit: int = 200
    ollama_model: Optional[str] = None
    message_count: int = 0
    last_spontaneous_message: Optional[datetime] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    
    @classmethod
    def from_db_row(cls, row: tuple) -> 'ChannelConfig':
        """Create ChannelConfig instance from database row."""
        return cls(
            channel=row[0],
            message_threshold=row[1],
            spontaneous_cooldown=row[2],
            response_cooldown=row[3],
            context_limit=row[4],
            ollama_model=row[5],
            message_count=row[6],
            last_spontaneous_message=row[7] if row[7] and isinstance(row[7], datetime) else 
                                   (datetime.fromisoformat(str(row[7])) if row[7] else None),
            created_at=row[8] if isinstance(row[8], datetime) else datetime.fromisoformat(str(row[8])),
            updated_at=row[9] if isinstance(row[9], datetime) else datetime.fromisoformat(str(row[9]))
        )
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            'channel': self.channel,
            'message_threshold': self.message_threshold,
            'spontaneous_cooldown': self.spontaneous_cooldown,
            'response_cooldown': self.response_cooldown,
            'context_limit': self.context_limit,
            'ollama_model': self.ollama_model,
            'message_count': self.message_count,
            'last_spontaneous_message': self.last_spontaneous_message.isoformat() if self.last_spontaneous_message else None,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }


@dataclass
class UserResponseCooldown:
    """Represents per-user response cooldown tracking."""
    id: Optional[int]
    channel: str
    user_id: str
    last_response_time: datetime
    
    @classmethod
    def from_db_row(cls, row: tuple) -> 'UserResponseCooldown':
        """Create UserResponseCooldown instance from database row."""
        return cls(
            id=row[0],
            channel=row[1],
            user_id=row[2],
            last_response_time=row[3] if isinstance(row[3], datetime) else datetime.fromisoformat(str(row[3]))
        )


@dataclass
class BotMetric:
    """Represents bot performance metrics."""
    id: Optional[int]
    channel: str
    metric_type: str  # 'response_time', 'success_rate', 'error_count'
    metric_value: float
    timestamp: datetime
    
    @classmethod
    def from_db_row(cls, row: tuple) -> 'BotMetric':
        """Create BotMetric instance from database row."""
        return cls(
            id=row[0],
            channel=row[1],
            metric_type=row[2],
            metric_value=float(row[3]),
            timestamp=row[4] if isinstance(row[4], datetime) else datetime.fromisoformat(str(row[4]))
        )


@dataclass
class AuthToken:
    """Represents OAuth authentication tokens."""
    id: Optional[int]
    access_token: str
    refresh_token: Optional[str]
    expires_at: Optional[datetime]
    bot_username: Optional[str]
    created_at: Optional[datetime]
    
    @classmethod
    def from_db_row(cls, row: tuple) -> 'AuthToken':
        """Create AuthToken instance from database row."""
        return cls(
            id=row[0],
            access_token=row[1],
            refresh_token=row[2],
            expires_at=row[3] if row[3] and isinstance(row[3], datetime) else 
                      (datetime.fromisoformat(str(row[3])) if row[3] else None),
            bot_username=row[4],
            created_at=row[5] if isinstance(row[5], datetime) else datetime.fromisoformat(str(row[5]))
        )


@dataclass
class MessageEvent:
    """Represents an incoming message event from IRC."""
    channel: str
    user_id: str
    user_display_name: str
    message_id: str
    content: str
    timestamp: datetime
    badges: Dict[str, str]
    
    def to_message(self) -> Message:
        """Convert to Message model for database storage."""
        return Message(
            id=None,
            message_id=self.message_id,
            channel=self.channel,
            user_id=self.user_id,
            user_display_name=self.user_display_name,
            message_content=self.content,
            timestamp=self.timestamp
        )