# Twitch Ollama Chatbot - Architecture & Development Guidelines

## Overview

This steering document provides architectural principles and development guidelines for implementing the Twitch Ollama Chatbot. These guidelines ensure maintainable, testable, and extensible code that follows best practices.

## Modular Architecture

### Core Modules

The system must be organized into distinct, loosely-coupled modules:

1. **IRC Handler Module** (`irc/`)
   - Twitch IRC connection management
   - Message parsing and event handling
   - Reconnection logic and error handling
   - Channel management (join/leave)

2. **Ollama Integration Module** (`ollama/`)
   - API client for Ollama communication
   - Request/response handling with timeout management
   - Model selection and prompt formatting
   - Message length validation and truncation (500 character Twitch limit)
   - Error handling and retry logic

3. **Database Module** (`database/`)
   - Database connection management (SQLite/MySQL)
   - Message storage and retrieval operations
   - Schema management and migrations
   - Query optimization for context retrieval

4. **Message Processing Module** (`processing/`)
   - Content filtering (input/output)
   - Message generation triggers and timing
   - Context window management
   - Mention detection and response logic

5. **Configuration Module** (`config/`)
   - Environment variable handling
   - Per-channel settings management
   - Chat command parsing and validation
   - Settings persistence and retrieval

6. **Authentication Module** (`auth/`)
   - OAuth token management
   - Token refresh and validation
   - Secure storage of credentials
   - Username detection from OAuth response

### Module Interfaces

Each module must expose clear, well-defined interfaces:

```python
# Example interface pattern
class MessageProcessor:
    def filter_content(self, message: str) -> Optional[str]:
        """Filter message content, return None if blocked"""
        pass
    
    def should_generate(self, channel: str) -> bool:
        """Check if bot should generate a message for channel"""
        pass
    
    def build_context(self, channel: str, limit: int) -> List[Message]:
        """Build context window for message generation"""
        pass
```

## Database Design

### Schema Principles

- **Minimal data storage**: Only store essential fields (message_id, channel, user_id, user_display_name, message_content, timestamp)
- **Channel isolation**: Strict separation of data by channel
- **Privacy-focused**: No unnecessary user data collection
- **Efficient queries**: Optimized for context retrieval patterns
- **Content filtering**: Filtered messages are never stored in the database
- **Moderation support**: Use message_id for deletion events and user_id for ban/timeout events
- **Query optimization**: Order messages by timestamp and filter by channel for isolation
- **Retention policies**: Support automatic cleanup of old messages based on age or count limits per channel

### Required Tables

```sql
-- Core message storage
CREATE TABLE messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    message_id TEXT UNIQUE NOT NULL,
    channel TEXT NOT NULL,
    user_id TEXT NOT NULL,
    user_display_name TEXT NOT NULL,
    message_content TEXT NOT NULL,
    timestamp DATETIME NOT NULL,
    INDEX idx_channel_timestamp (channel, timestamp),
    INDEX idx_message_id (message_id),
    INDEX idx_user_id (user_id)
);

-- Channel-specific configuration
CREATE TABLE channel_config (
    channel TEXT PRIMARY KEY,
    message_threshold INTEGER DEFAULT 30,
    time_delay INTEGER DEFAULT 300,
    context_limit INTEGER DEFAULT 200,
    ollama_model TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- OAuth token storage (encrypted)
CREATE TABLE auth_tokens (
    id INTEGER PRIMARY KEY,
    access_token TEXT NOT NULL,
    refresh_token TEXT,
    expires_at DATETIME,
    bot_username TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

## Error Handling Strategy

### Graceful Degradation

- **Ollama unavailable**: Skip generation, continue monitoring
- **Database errors**: Log and attempt reconnection
- **IRC disconnection**: Auto-reconnect with exponential backoff
- **Content filtering failure**: Default to blocking suspicious content

### Logging Requirements

```python
# Structured logging with appropriate levels
logger.info("Bot started", extra={"channels": channels, "model": model})
logger.warning("Ollama timeout", extra={"channel": channel, "duration": duration})
logger.error("Database connection failed", extra={"error": str(e), "retry_count": retries})
```

## Security Guidelines

### Token Management

- Store OAuth tokens encrypted in database
- Implement automatic token refresh
- Never log sensitive authentication data
- Use secure random generation for any internal tokens

### Content Filtering

- Always filter before database storage
- Implement both input and output filtering
- Log blocked content with context for analysis
- Fail-safe: block when filtering system is unavailable

### Input Validation

- Validate all chat commands and parameters
- Sanitize database inputs to prevent injection
- Limit configuration values to reasonable ranges
- Validate Ollama responses before processing

## Configuration Management

### Environment Variables (Global Defaults)

```bash
# Database configuration
DATABASE_TYPE=sqlite  # or mysql
DATABASE_URL=./chatbot.db
MYSQL_HOST=localhost
MYSQL_USER=chatbot
MYSQL_PASSWORD=secure_password
MYSQL_DATABASE=twitch_bot

# Ollama configuration
OLLAMA_URL=http://localhost:11434
OLLAMA_MODEL=llama3.1
OLLAMA_TIMEOUT=30

# Twitch configuration
TWITCH_CLIENT_ID=your_client_id
TWITCH_CLIENT_SECRET=your_client_secret
TWITCH_CHANNELS=channel1,channel2,channel3

# Content filtering
CONTENT_FILTER_ENABLED=true
BLOCKED_WORDS_FILE=./blocked_words.txt
```

### Per-Channel Settings

Stored in database, configurable via `!clank` commands:
- `threshold`: Message count trigger (default: 30)
- `delay`: Minimum time between bot messages in seconds (default: 300)
- `context`: Maximum context window size (default: 200)
- `model`: Ollama model to use (inherits global default)

## Testing Strategy

### Unit Testing

Each module must have comprehensive unit tests:

```python
# Example test structure
class TestMessageProcessor:
    def test_content_filtering_blocks_inappropriate_content(self):
        processor = MessageProcessor()
        result = processor.filter_content("inappropriate message")
        assert result is None
    
    def test_mention_detection_case_insensitive(self):
        processor = MessageProcessor()
        assert processor.is_mention("@BotName hello", "botname")
        assert processor.is_mention("botname what's up", "BotName")
```

### Integration Testing

- Test database operations with real database
- Test Ollama integration with mock server
- Test IRC connection handling
- Test end-to-end message flow

### Performance Testing

- Context retrieval performance with large message histories
- Database query optimization validation
- Memory usage monitoring during extended operation

## Deployment Guidelines

### Installation Requirements

```bash
# Python dependencies
pip install -r requirements.txt

# Required packages
- twitchio>=2.0.0
- aiohttp>=3.8.0
- sqlalchemy>=2.0.0
- python-dotenv>=1.0.0
- better-profanity>=0.7.0  # or alternative content filter
```

### Service Configuration

Support both development and production deployment:

```python
# Development: Direct script execution
python -m chatbot.main

# Production: Systemd service
[Unit]
Description=Twitch Ollama Chatbot
After=network.target

[Service]
Type=simple
User=chatbot
WorkingDirectory=/opt/twitch-chatbot
ExecStart=/opt/twitch-chatbot/venv/bin/python -m chatbot.main
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

## Code Quality Standards

### Python Style

- Follow PEP 8 style guidelines
- Use type hints for all function signatures
- Implement proper docstrings for all public methods
- Use async/await for I/O operations

### Code Organization

```
chatbot/
├── __init__.py
├── main.py              # Entry point
├── config/
│   ├── __init__.py
│   ├── settings.py      # Configuration management
│   └── commands.py      # Chat command handling
├── irc/
│   ├── __init__.py
│   ├── client.py        # IRC client implementation
│   └── handlers.py      # Message event handlers
├── ollama/
│   ├── __init__.py
│   └── client.py        # Ollama API client with prompt handling
├── database/
│   ├── __init__.py
│   ├── models.py        # Database models
│   ├── operations.py    # CRUD operations
│   └── migrations.py    # Schema management
├── processing/
│   ├── __init__.py
│   ├── filters.py       # Content filtering
│   ├── triggers.py      # Message generation triggers
│   └── context.py       # Context window management
└── auth/
    ├── __init__.py
    ├── oauth.py         # OAuth handling
    └── tokens.py        # Token management
```

## Performance Considerations

### Database Optimization

- Index frequently queried columns (channel, timestamp)
- Implement automatic cleanup of old messages
- Use connection pooling for MySQL deployments
- Optimize context retrieval queries

### Memory Management

- Limit in-memory message caches
- Implement proper cleanup of old data
- Monitor memory usage in long-running deployments
- Use generators for large data processing

### Concurrency

- Use async/await for I/O operations
- Implement proper connection pooling
- Handle multiple channels concurrently
- Avoid blocking operations in main event loop

## Future Extensibility

### Model Customization

Design the system to support future model enhancements:

- **Channel-specific models**: Support for loading different models per channel
- **Fine-tuned models**: Integration with custom-trained models based on channel chat data
- **Model parameters**: Configurable temperature, top-p, and other generation parameters
- **Prompt engineering**: Optimized system prompts for chat message generation

### Configuration Extensions

- Support for additional Ollama parameters (temperature, top-p, etc.)
- Custom content filtering rules per channel
- Advanced trigger conditions (user activity patterns, time-based triggers)
- Model training data collection for future fine-tuning

This architecture ensures the chatbot is maintainable, testable, and ready for future enhancements while following Python best practices and security guidelines.