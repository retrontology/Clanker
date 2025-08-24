# Twitch Ollama Chatbot

A Python-based Twitch chatbot that integrates with Ollama to generate contextually relevant chat messages based on recent conversation history.

## Project Structure

```
chatbot/
├── __init__.py              # Package initialization
├── main.py                  # Main entry point
├── config/
│   ├── __init__.py
│   ├── settings.py          # Global configuration management
│   └── commands.py          # Chat command handling
├── irc/
│   ├── __init__.py
│   ├── client.py            # Twitch IRC client implementation
│   └── handlers.py          # Message event handlers
├── ollama/
│   ├── __init__.py
│   └── client.py            # Ollama API client
├── database/
│   ├── __init__.py
│   ├── models.py            # Database models and schema
│   ├── operations.py        # CRUD operations
│   └── migrations.py        # Schema management
├── processing/
│   ├── __init__.py
│   ├── filters.py           # Content filtering
│   ├── triggers.py          # Message generation triggers
│   └── context.py           # Context window management
└── auth/
    ├── __init__.py
    ├── oauth.py             # OAuth handling
    └── tokens.py            # Token management
```

## Installation

1. Clone the repository
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Copy `.env.example` to `.env` and configure your settings
4. Run the bot:
   ```bash
   python -m chatbot.main
   ```

## Configuration

The bot uses environment variables for configuration. See `.env.example` for all available options.

### Required Configuration

- `OLLAMA_MODEL`: The Ollama model to use for generation
- `TWITCH_CLIENT_ID`: Your Twitch application client ID
- `TWITCH_CLIENT_SECRET`: Your Twitch application client secret
- `TWITCH_CHANNELS`: Comma-separated list of channels to join

### Optional Configuration

- `DATABASE_TYPE`: Database type (sqlite or mysql, defaults to sqlite)
- `OLLAMA_URL`: Ollama server URL (defaults to http://localhost:11434)
- `OLLAMA_TIMEOUT`: Request timeout in seconds (defaults to 30)
- `CONTENT_FILTER_ENABLED`: Enable content filtering (defaults to true)
- `LOG_LEVEL`: Logging level (defaults to INFO)

## Development Status

This project is currently under development. The basic project structure has been set up, but individual modules are not yet implemented.

## License

[Add your license information here]