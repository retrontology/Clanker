# Configuration Reference - Twitch Ollama Chatbot

This document provides a comprehensive reference for all configuration options available in the Twitch Ollama Chatbot.

## Table of Contents

- [Environment Variables](#environment-variables)
- [Chat Commands](#chat-commands)
- [Database Configuration](#database-configuration)
- [Content Filtering](#content-filtering)
- [Performance Tuning](#performance-tuning)
- [Security Settings](#security-settings)

## Environment Variables

Environment variables are set in the `.env` file and control global bot behavior. Changes require a service restart.

### Database Configuration

#### `DATABASE_TYPE`
- **Type**: String
- **Default**: `sqlite`
- **Options**: `sqlite`, `mysql`
- **Description**: Database backend to use
- **Example**: `DATABASE_TYPE=sqlite`

#### `DATABASE_URL`
- **Type**: String
- **Default**: `./chatbot.db`
- **Description**: SQLite database file path (only used when `DATABASE_TYPE=sqlite`)
- **Example**: `DATABASE_URL=/opt/twitch-ollama-chatbot/data/chatbot.db`

#### MySQL Configuration (when `DATABASE_TYPE=mysql`)

#### `MYSQL_HOST`
- **Type**: String
- **Default**: `localhost`
- **Description**: MySQL server hostname or IP address
- **Example**: `MYSQL_HOST=192.168.1.100`

#### `MYSQL_PORT`
- **Type**: Integer
- **Default**: `3306`
- **Description**: MySQL server port
- **Example**: `MYSQL_PORT=3306`

#### `MYSQL_USER`
- **Type**: String
- **Required**: Yes (when using MySQL)
- **Description**: MySQL username for bot database access
- **Example**: `MYSQL_USER=chatbot`

#### `MYSQL_PASSWORD`
- **Type**: String
- **Required**: Yes (when using MySQL)
- **Description**: MySQL password for bot database access
- **Example**: `MYSQL_PASSWORD=secure_password_here`

#### `MYSQL_DATABASE`
- **Type**: String
- **Required**: Yes (when using MySQL)
- **Description**: MySQL database name
- **Example**: `MYSQL_DATABASE=twitch_bot`

### Ollama Configuration

#### `OLLAMA_URL`
- **Type**: String
- **Default**: `http://localhost:11434`
- **Description**: Ollama server URL
- **Example**: `OLLAMA_URL=http://192.168.1.50:11434`

#### `OLLAMA_MODEL`
- **Type**: String
- **Default**: `llama3.1`
- **Description**: Default Ollama model for message generation
- **Example**: `OLLAMA_MODEL=llama3.1`
- **Note**: Can be overridden per channel using chat commands

#### `OLLAMA_TIMEOUT`
- **Type**: Integer
- **Default**: `30`
- **Description**: Timeout in seconds for Ollama API requests
- **Example**: `OLLAMA_TIMEOUT=45`
- **Range**: 10-120 seconds

### Twitch Configuration

#### `TWITCH_CLIENT_ID`
- **Type**: String
- **Required**: Yes
- **Description**: Twitch application client ID from developer console
- **Example**: `TWITCH_CLIENT_ID=abc123def456ghi789`

#### `TWITCH_CLIENT_SECRET`
- **Type**: String
- **Required**: Yes
- **Description**: Twitch application client secret from developer console
- **Example**: `TWITCH_CLIENT_SECRET=secret123abc456def`

#### `TWITCH_CHANNELS`
- **Type**: String (comma-separated)
- **Required**: Yes
- **Description**: List of Twitch channels to join (without # prefix)
- **Example**: `TWITCH_CHANNELS=channel1,channel2,channel3`
- **Note**: Channel names must be lowercase

### Authentication Configuration

#### `TOKEN_ENCRYPTION_KEY`
- **Type**: String (Base64)
- **Default**: Auto-generated on first run
- **Description**: Encryption key for storing OAuth tokens securely
- **Example**: `TOKEN_ENCRYPTION_KEY=gAAAAABh...` (Base64 encoded)
- **Generation**: `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`

### Content Filtering Configuration

#### `CONTENT_FILTER_ENABLED`
- **Type**: Boolean
- **Default**: `true`
- **Description**: Enable/disable content filtering
- **Example**: `CONTENT_FILTER_ENABLED=true`
- **Options**: `true`, `false`

#### `BLOCKED_WORDS_FILE`
- **Type**: String
- **Default**: `./blocked_words.txt`
- **Description**: Path to blocked words file
- **Example**: `BLOCKED_WORDS_FILE=/opt/twitch-ollama-chatbot/blocked_words.txt`

### Logging Configuration

#### `LOG_LEVEL`
- **Type**: String
- **Default**: `INFO`
- **Description**: Logging level
- **Options**: `DEBUG`, `INFO`, `WARNING`, `ERROR`
- **Example**: `LOG_LEVEL=INFO`

#### `LOG_FORMAT`
- **Type**: String
- **Default**: `console`
- **Description**: Log output format
- **Options**: `console`, `json`
- **Example**: `LOG_FORMAT=json`

#### `LOG_FILE`
- **Type**: String
- **Default**: None (console only)
- **Description**: Path to log file (optional)
- **Example**: `LOG_FILE=/opt/twitch-ollama-chatbot/logs/chatbot.log`

### Resource Management Configuration

#### `MEMORY_WARNING_MB`
- **Type**: Integer
- **Default**: `512`
- **Description**: Memory usage warning threshold in MB
- **Example**: `MEMORY_WARNING_MB=1024`

#### `MEMORY_CRITICAL_MB`
- **Type**: Integer
- **Default**: `1024`
- **Description**: Memory usage critical threshold in MB
- **Example**: `MEMORY_CRITICAL_MB=2048`

#### `DISK_WARNING_PERCENT`
- **Type**: Integer
- **Default**: `85`
- **Description**: Disk usage warning threshold as percentage
- **Example**: `DISK_WARNING_PERCENT=80`

#### `DISK_CRITICAL_PERCENT`
- **Type**: Integer
- **Default**: `95`
- **Description**: Disk usage critical threshold as percentage
- **Example**: `DISK_CRITICAL_PERCENT=90`

#### `MESSAGE_RETENTION_DAYS`
- **Type**: Integer
- **Default**: `30`
- **Description**: Number of days to retain chat messages
- **Example**: `MESSAGE_RETENTION_DAYS=90`

#### `METRICS_RETENTION_DAYS`
- **Type**: Integer
- **Default**: `7`
- **Description**: Number of days to retain performance metrics
- **Example**: `METRICS_RETENTION_DAYS=30`

#### `CLEANUP_INTERVAL_MINUTES`
- **Type**: Integer
- **Default**: `60`
- **Description**: Interval between cleanup operations in minutes
- **Example**: `CLEANUP_INTERVAL_MINUTES=30`

### Default Channel Settings

These can be overridden per channel using chat commands:

#### `DEFAULT_MESSAGE_THRESHOLD`
- **Type**: Integer
- **Default**: `30`
- **Description**: Default message count threshold for spontaneous generation
- **Example**: `DEFAULT_MESSAGE_THRESHOLD=50`

#### `DEFAULT_SPONTANEOUS_COOLDOWN`
- **Type**: Integer
- **Default**: `300`
- **Description**: Default cooldown in seconds between spontaneous messages
- **Example**: `DEFAULT_SPONTANEOUS_COOLDOWN=600`

#### `DEFAULT_RESPONSE_COOLDOWN`
- **Type**: Integer
- **Default**: `60`
- **Description**: Default cooldown in seconds for user mention responses
- **Example**: `DEFAULT_RESPONSE_COOLDOWN=120`

#### `DEFAULT_CONTEXT_LIMIT`
- **Type**: Integer
- **Default**: `200`
- **Description**: Default maximum number of messages in context window
- **Example**: `DEFAULT_CONTEXT_LIMIT=150`

## Chat Commands

Chat commands allow real-time configuration changes without restarting the bot. Only broadcasters and moderators can use these commands.

### Command Format

All commands follow the pattern: `!clank <setting> [value]`

- Without value: Shows current setting
- With value: Updates the setting

### Available Commands

#### `!clank threshold [value]`
- **Description**: Message count threshold for spontaneous generation
- **Range**: 5-200 messages
- **Default**: 30
- **Examples**:
  - `!clank threshold` - Show current threshold
  - `!clank threshold 45` - Set threshold to 45 messages

#### `!clank spontaneous [value]`
- **Description**: Cooldown between spontaneous messages in seconds
- **Range**: 60-3600 seconds (1 minute to 1 hour)
- **Default**: 300 (5 minutes)
- **Examples**:
  - `!clank spontaneous` - Show current cooldown
  - `!clank spontaneous 600` - Set cooldown to 10 minutes

#### `!clank response [value]`
- **Description**: Per-user cooldown for mention responses in seconds
- **Range**: 10-1800 seconds (10 seconds to 30 minutes)
- **Default**: 60 (1 minute)
- **Examples**:
  - `!clank response` - Show current response cooldown
  - `!clank response 120` - Set response cooldown to 2 minutes

#### `!clank context [value]`
- **Description**: Maximum number of messages in context window
- **Range**: 50-500 messages
- **Default**: 200
- **Examples**:
  - `!clank context` - Show current context limit
  - `!clank context 150` - Set context limit to 150 messages

#### `!clank model [value]`
- **Description**: Ollama model to use for this channel
- **Default**: Global default from `OLLAMA_MODEL`
- **Examples**:
  - `!clank model` - Show current model
  - `!clank model llama3.1` - Set model to llama3.1
  - `!clank model codellama` - Set model to codellama

#### `!clank status`
- **Description**: Show bot status and performance information
- **Output includes**:
  - Ollama connectivity and model information
  - Current channel configuration
  - Recent performance metrics
  - Memory and resource usage
- **Example**: `!clank status`

#### `!clank reset`
- **Description**: Reset all channel settings to global defaults
- **Example**: `!clank reset`
- **Confirmation**: Requires typing `!clank reset confirm`

### Command Permissions

Commands are restricted based on Twitch IRC badges:

- **Broadcaster**: All commands
- **Moderator**: All commands
- **VIP**: Status command only
- **Regular users**: No commands

## Database Configuration

### SQLite Configuration

SQLite is the default database and requires no additional setup:

```env
DATABASE_TYPE=sqlite
DATABASE_URL=/opt/twitch-ollama-chatbot/data/chatbot.db
```

**Advantages**:
- No additional software required
- Simple backup (copy file)
- Good performance for small to medium deployments

**Limitations**:
- Single file database
- Limited concurrent write performance

### MySQL Configuration

For high-traffic deployments or when you need advanced database features:

```env
DATABASE_TYPE=mysql
MYSQL_HOST=localhost
MYSQL_PORT=3306
MYSQL_USER=chatbot
MYSQL_PASSWORD=secure_password
MYSQL_DATABASE=twitch_bot
```

**Setup Steps**:

1. Install MySQL server
2. Create database and user:
   ```sql
   CREATE DATABASE twitch_bot CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
   CREATE USER 'chatbot'@'localhost' IDENTIFIED BY 'secure_password';
   GRANT ALL PRIVILEGES ON twitch_bot.* TO 'chatbot'@'localhost';
   FLUSH PRIVILEGES;
   ```

**Advantages**:
- Better concurrent performance
- Advanced features (replication, clustering)
- Better for multiple bot instances

## Content Filtering

### Blocked Words File Format

The `blocked_words.txt` file supports:

- One word/phrase per line
- Comments starting with `#`
- Empty lines (ignored)
- Case-insensitive matching

**Example**:
```
# Hate speech and slurs
badword1
badword2

# Spam patterns
buy followers
free money

# Custom additions
custom_blocked_phrase
```

### Filtering Behavior

- **Input filtering**: Applied to incoming chat messages before storage
- **Output filtering**: Applied to bot-generated messages before sending
- **Normalization**: Handles leetspeak, spacing tricks, and evasion attempts
- **Fail-safe**: When filtering fails, content is blocked rather than allowed

### Custom Filter Rules

You can customize filtering by:

1. Editing the blocked words file
2. Restarting the service (changes are loaded on startup)
3. Using different blocked words files per deployment

## Performance Tuning

### Memory Optimization

For low-memory environments:
```env
MEMORY_WARNING_MB=256
MEMORY_CRITICAL_MB=512
MESSAGE_RETENTION_DAYS=7
CLEANUP_INTERVAL_MINUTES=30
```

### High-Traffic Optimization

For busy channels:
```env
# Use MySQL for better performance
DATABASE_TYPE=mysql

# Increase resource limits
MEMORY_WARNING_MB=2048
MEMORY_CRITICAL_MB=4096

# Longer retention for better context
MESSAGE_RETENTION_DAYS=90
DEFAULT_CONTEXT_LIMIT=300

# More frequent cleanup
CLEANUP_INTERVAL_MINUTES=15
```

### Context Window Tuning

Balance between context quality and performance:

- **Small channels** (< 100 viewers): 100-150 messages
- **Medium channels** (100-1000 viewers): 150-250 messages  
- **Large channels** (1000+ viewers): 200-500 messages

### Rate Limiting Tuning

Adjust based on channel activity:

**Low activity channels**:
```
DEFAULT_MESSAGE_THRESHOLD=15
DEFAULT_SPONTANEOUS_COOLDOWN=180
```

**High activity channels**:
```
DEFAULT_MESSAGE_THRESHOLD=50
DEFAULT_SPONTANEOUS_COOLDOWN=600
```

## Security Settings

### Token Security

- Always use `TOKEN_ENCRYPTION_KEY` in production
- Store `.env` file with restricted permissions (640)
- Regularly rotate OAuth tokens
- Use dedicated bot account, not your main account

### File Permissions

Recommended permissions:
```bash
# Application directory
chmod 755 /opt/twitch-ollama-chatbot

# Configuration file
chmod 640 /opt/twitch-ollama-chatbot/.env

# Data and log directories
chmod 750 /opt/twitch-ollama-chatbot/data
chmod 750 /opt/twitch-ollama-chatbot/logs

# Database file
chmod 640 /opt/twitch-ollama-chatbot/data/chatbot.db
```

### Network Security

- Run Ollama on localhost when possible
- Use firewall rules to restrict access
- Consider VPN for remote Ollama servers
- Monitor network traffic for anomalies

### Systemd Security

The provided systemd service includes security hardening:

- `NoNewPrivileges=true`
- `PrivateTmp=true`
- `ProtectSystem=strict`
- `ProtectHome=true`
- Memory and CPU limits

### Backup Security

- Encrypt backups containing sensitive data
- Store backups in secure locations
- Regularly test backup restoration
- Implement backup retention policies

## Configuration Examples

### Development Setup

```env
# Development configuration
DATABASE_TYPE=sqlite
DATABASE_URL=./dev_chatbot.db
OLLAMA_URL=http://localhost:11434
OLLAMA_MODEL=llama3.1
TWITCH_CHANNELS=your_test_channel
LOG_LEVEL=DEBUG
LOG_FORMAT=console
DEFAULT_MESSAGE_THRESHOLD=5
DEFAULT_SPONTANEOUS_COOLDOWN=60
```

### Production Setup

```env
# Production configuration
DATABASE_TYPE=mysql
MYSQL_HOST=localhost
MYSQL_USER=chatbot
MYSQL_PASSWORD=secure_password
MYSQL_DATABASE=twitch_bot
OLLAMA_URL=http://localhost:11434
OLLAMA_MODEL=llama3.1
TWITCH_CHANNELS=channel1,channel2,channel3
TOKEN_ENCRYPTION_KEY=generated_key_here
LOG_LEVEL=INFO
LOG_FORMAT=json
LOG_FILE=/opt/twitch-ollama-chatbot/logs/chatbot.log
MEMORY_WARNING_MB=1024
MEMORY_CRITICAL_MB=2048
MESSAGE_RETENTION_DAYS=90
```

### Multi-Channel Setup

```env
# Multi-channel configuration
TWITCH_CHANNELS=gaming_channel,music_channel,art_channel
DEFAULT_MESSAGE_THRESHOLD=40
DEFAULT_SPONTANEOUS_COOLDOWN=450
DEFAULT_CONTEXT_LIMIT=250
MESSAGE_RETENTION_DAYS=60
CLEANUP_INTERVAL_MINUTES=30
```

For more information, see the [Installation Guide](INSTALLATION.md) and [Troubleshooting Guide](TROUBLESHOOTING.md).