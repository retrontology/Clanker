# Twitch Ollama Chatbot

A Python-based Twitch chatbot that integrates with Ollama to generate contextually relevant chat messages. The bot analyzes recent chat messages and generates natural responses that fit the conversation flow, creating engaging interactions in Twitch channels.

## Features

- **Multi-channel support**: Operate in multiple Twitch channels simultaneously
- **Context-aware generation**: Uses recent chat history to generate relevant messages
- **Dual message types**: Spontaneous messages and direct mention responses
- **Configurable rate limiting**: Separate cooldowns for automatic and response messages
- **Content filtering**: Built-in filtering for inappropriate content
- **Real-time configuration**: Chat commands for moderators to adjust settings
- **Persistent storage**: SQLite or MySQL database support
- **Moderation integration**: Respects bans, timeouts, and message deletions
- **Performance monitoring**: Built-in metrics and resource management
- **Docker support**: Easy deployment with Docker and Docker Compose

## Quick Start

### Prerequisites

- Python 3.11+
- [Ollama](https://ollama.ai/) server running locally or remotely
- Twitch account for the bot
- Twitch Developer Application (for OAuth credentials)

### Installation

1. **Clone the repository**:
   ```bash
   git clone https://github.com/your-repo/twitch-ollama-chatbot.git
   cd twitch-ollama-chatbot
   ```

2. **Install with Docker** (recommended):
   ```bash
   # Copy and configure environment
   cp .env.example .env
   nano .env  # Configure your settings
   
   # Start the bot
   docker-compose up -d
   ```

3. **Or install manually on Linux**:
   ```bash
   # Run automated installation
   sudo ./deploy/install.sh
   
   # Configure settings
   sudo nano /opt/twitch-ollama-chatbot/.env
   
   # Start the service
   sudo systemctl start twitch-ollama-chatbot
   ```

### Configuration

1. **Set up Twitch OAuth**:
   - Create a Twitch application at [dev.twitch.tv](https://dev.twitch.tv/console)
   - Generate an OAuth token with `chat:read` and `chat:edit` scopes
   - Add your credentials to the `.env` file

2. **Configure Ollama**:
   - Ensure Ollama is running: `curl http://localhost:11434/api/tags`
   - Pull a model: `ollama pull llama3.1`
   - Set the model in your configuration

3. **Set channel list**:
   ```env
   TWITCH_CHANNELS=channel1,channel2,channel3
   ```

## How It Works

### Message Generation

The bot operates with two types of message generation:

1. **Spontaneous Messages**: Generated automatically when:
   - Message count threshold is reached (default: 30 messages)
   - Minimum time has passed since last bot message (default: 5 minutes)
   - Adequate chat context is available

2. **Response Messages**: Generated when users mention the bot:
   - Triggered by `@botname` or `botname` in messages
   - Uses recent chat context plus the user's message
   - Subject to per-user cooldowns (default: 1 minute)

### Context Management

- Maintains separate chat history for each channel
- Configurable context window size (default: 200 messages)
- Filters out bot messages, system messages, and inappropriate content
- Respects moderation actions (removes banned users' messages)

### Rate Limiting

- **Channel-level cooldowns**: Prevent spam in channels
- **User-level cooldowns**: Prevent individual users from spamming mentions
- **Independent systems**: Response and spontaneous cooldowns don't interfere
- **Configurable per channel**: Adjust settings via chat commands

## Chat Commands

Moderators and broadcasters can configure the bot using chat commands:

```
!clank status                    # Show bot status and performance
!clank threshold [value]         # Set/show message count threshold
!clank spontaneous [seconds]     # Set/show spontaneous message cooldown
!clank response [seconds]        # Set/show user response cooldown
!clank context [count]           # Set/show context window size
!clank model [model_name]        # Set/show Ollama model for this channel
!clank reset                     # Reset all settings to defaults
```

## Architecture

The bot is built with a modular architecture:

- **IRC Handler**: Manages Twitch IRC connections and events
- **Ollama Client**: Handles AI model communication
- **Database Layer**: Manages persistent storage (SQLite/MySQL)
- **Message Processor**: Coordinates filtering and generation
- **Configuration Manager**: Handles settings and chat commands
- **Authentication Manager**: Manages OAuth tokens securely

## Deployment Options

### Docker Deployment

```bash
# Development
docker-compose up -d

# Production with MySQL
docker-compose -f deploy/docker/docker-compose.production.yml up -d
```

### Linux Service

```bash
# Install as systemd service
sudo ./deploy/install.sh

# Manage service
sudo systemctl start twitch-ollama-chatbot
sudo systemctl status twitch-ollama-chatbot
sudo journalctl -u twitch-ollama-chatbot -f
```

### Manual Development

```bash
# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
pip install -e .

# Run directly
python -m chatbot.main
```

## Configuration

### Environment Variables

Key configuration options:

```env
# Database
DATABASE_TYPE=sqlite                    # or mysql
DATABASE_URL=./chatbot.db

# Ollama
OLLAMA_URL=http://localhost:11434
OLLAMA_MODEL=llama3.1
OLLAMA_TIMEOUT=30

# Twitch
TWITCH_CLIENT_ID=your_client_id
TWITCH_CLIENT_SECRET=your_client_secret
TWITCH_CHANNELS=channel1,channel2

# Content Filtering
CONTENT_FILTER_ENABLED=true
BLOCKED_WORDS_FILE=./blocked_words.txt

# Logging
LOG_LEVEL=INFO
LOG_FORMAT=console
```

### Per-Channel Settings

Each channel can have individual settings:

- Message threshold (5-200 messages)
- Spontaneous cooldown (60-3600 seconds)
- Response cooldown (10-1800 seconds)
- Context window size (50-500 messages)
- Ollama model selection

## Security Features

- **Token encryption**: OAuth tokens stored encrypted in database
- **Content filtering**: Input and output filtering for inappropriate content
- **Permission system**: Chat commands restricted to moderators/broadcasters
- **Sandboxed execution**: Systemd service with security restrictions
- **Resource limits**: Memory and CPU limits to prevent abuse

## Monitoring and Maintenance

### Performance Monitoring

- Built-in metrics collection
- Resource usage monitoring
- Response time tracking
- Error rate monitoring

### Maintenance Tasks

- Automatic cleanup of old messages and metrics
- Database optimization and maintenance
- Log rotation and management
- Backup and recovery procedures

### Health Checks

```bash
# Service health
sudo systemctl status twitch-ollama-chatbot

# Performance metrics
!clank status  # In chat

# Resource usage
htop
df -h
```

## Documentation

- [Installation Guide](docs/INSTALLATION.md) - Detailed setup instructions
- [Configuration Reference](docs/CONFIGURATION.md) - Complete configuration options
- [Troubleshooting Guide](docs/TROUBLESHOOTING.md) - Common issues and solutions
- [API Documentation](docs/API.md) - Internal API reference

## Development

### Running Tests

```bash
# Install test dependencies
pip install -r tests/requirements.txt

# Run all tests
python -m pytest

# Run specific test categories
python -m pytest tests/test_integration_*.py
python -m pytest tests/test_performance.py
```

### Code Structure

```
chatbot/
├── auth/           # OAuth and authentication
├── config/         # Configuration management
├── database/       # Database operations and models
├── irc/           # Twitch IRC client and handlers
├── logging/       # Structured logging and metrics
├── ollama/        # Ollama API client
├── processing/    # Message processing and filtering
└── main.py        # Application entry point
```

### Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests for new functionality
5. Ensure all tests pass
6. Submit a pull request

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Support

- **Issues**: Report bugs and request features on GitHub Issues
- **Documentation**: Check the docs/ directory for detailed guides
- **Community**: Join discussions in GitHub Discussions

## Acknowledgments

- [Ollama](https://ollama.ai/) for the local LLM server
- [TwitchIO](https://github.com/TwitchIO/TwitchIO) for Twitch IRC integration
- The open-source community for various dependencies and inspiration