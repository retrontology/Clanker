# Installation Guide - Twitch Ollama Chatbot

This guide will walk you through installing and setting up the Twitch Ollama Chatbot on your system.

## Table of Contents

- [Prerequisites](#prerequisites)
- [Quick Start with Docker](#quick-start-with-docker)
- [Manual Installation on Linux](#manual-installation-on-linux)
- [OAuth Configuration](#oauth-configuration)
- [Initial Setup](#initial-setup)
- [Verification](#verification)
- [Troubleshooting](#troubleshooting)

## Prerequisites

### System Requirements

- **Operating System**: Linux (Ubuntu 20.04+, Debian 11+, CentOS 8+, or similar)
- **Python**: 3.11 or higher
- **Memory**: Minimum 512MB RAM, recommended 1GB+
- **Storage**: 2GB free space minimum
- **Network**: Internet connection for Twitch IRC and Ollama API

### Required Services

1. **Ollama Server**: Must be running and accessible
   - Install from: https://ollama.ai/
   - Default URL: `http://localhost:11434`
   - Required model: `llama3.1` (or your preferred model)

2. **Database** (choose one):
   - **SQLite**: Built-in, no setup required (recommended for small deployments)
   - **MySQL**: For high-traffic deployments (optional)

## Quick Start with Docker

### 1. Clone the Repository

```bash
git clone https://github.com/your-repo/twitch-ollama-chatbot.git
cd twitch-ollama-chatbot
```

### 2. Configure Environment

```bash
# Copy environment template
cp .env.example .env

# Edit configuration (see OAuth Configuration section below)
nano .env
```

### 3. Start with Docker Compose

```bash
# Start the chatbot
docker-compose up -d

# View logs
docker-compose logs -f chatbot

# Stop the chatbot
docker-compose down
```

## Manual Installation on Linux

### 1. Automated Installation

The easiest way to install on Linux is using the automated installation script:

```bash
# Clone the repository
git clone https://github.com/your-repo/twitch-ollama-chatbot.git
cd twitch-ollama-chatbot

# Run the installation script
sudo ./deploy/install.sh
```

This script will:
- Create a dedicated `chatbot` user
- Install the application to `/opt/twitch-ollama-chatbot`
- Set up a Python virtual environment
- Install all dependencies
- Configure systemd service
- Set up log rotation

### 2. Manual Installation Steps

If you prefer manual installation:

#### Step 1: Create User and Directories

```bash
# Create system user
sudo groupadd --system chatbot
sudo useradd --system --gid chatbot --home-dir /opt/twitch-ollama-chatbot \
             --shell /bin/false --comment "Twitch Ollama Chatbot" chatbot

# Create directories
sudo mkdir -p /opt/twitch-ollama-chatbot/{data,logs}
sudo chown -R chatbot:chatbot /opt/twitch-ollama-chatbot
```

#### Step 2: Install Application

```bash
# Copy application files
sudo cp -r chatbot/ /opt/twitch-ollama-chatbot/
sudo cp requirements.txt setup.py blocked_words.txt /opt/twitch-ollama-chatbot/
sudo cp .env.example /opt/twitch-ollama-chatbot/.env

# Set ownership
sudo chown -R chatbot:chatbot /opt/twitch-ollama-chatbot
sudo chmod 640 /opt/twitch-ollama-chatbot/.env
```

#### Step 3: Create Virtual Environment

```bash
# Create and activate virtual environment
sudo -u chatbot python3 -m venv /opt/twitch-ollama-chatbot/venv
sudo -u chatbot /opt/twitch-ollama-chatbot/venv/bin/pip install --upgrade pip
sudo -u chatbot /opt/twitch-ollama-chatbot/venv/bin/pip install -r /opt/twitch-ollama-chatbot/requirements.txt
sudo -u chatbot /opt/twitch-ollama-chatbot/venv/bin/pip install -e /opt/twitch-ollama-chatbot
```

#### Step 4: Install Systemd Service

```bash
# Copy service file
sudo cp deploy/systemd/twitch-ollama-chatbot.service /etc/systemd/system/

# Reload systemd and enable service
sudo systemctl daemon-reload
sudo systemctl enable twitch-ollama-chatbot.service
```

## OAuth Configuration

### 1. Create Twitch Application

1. Go to the [Twitch Developer Console](https://dev.twitch.tv/console)
2. Click "Register Your Application"
3. Fill in the details:
   - **Name**: Your bot name (e.g., "MyTwitchBot")
   - **OAuth Redirect URLs**: `http://localhost:3000` (for local setup)
   - **Category**: Chat Bot
4. Click "Create"
5. Note down your **Client ID** and **Client Secret**

### 2. Generate OAuth Token

You have several options to generate an OAuth token:

#### Option A: Using Twitch CLI (Recommended)

```bash
# Install Twitch CLI
# Ubuntu/Debian:
sudo apt install twitch-cli

# Generate token
twitch token -u -s 'chat:read chat:edit'
```

#### Option B: Manual OAuth Flow

1. Replace `YOUR_CLIENT_ID` in this URL:
```
https://id.twitch.tv/oauth2/authorize?client_id=YOUR_CLIENT_ID&redirect_uri=http://localhost:3000&response_type=code&scope=chat:read+chat:edit
```

2. Visit the URL in your browser
3. Authorize the application
4. Copy the authorization code from the redirect URL
5. Exchange the code for a token using curl or a tool like Postman

#### Option C: Using Third-Party Tools

- [Twitch Token Generator](https://twitchtokengenerator.com/)
- Make sure to select scopes: `chat:read` and `chat:edit`

### 3. Configure Environment Variables

Edit your `.env` file:

```bash
# Edit the configuration file
sudo nano /opt/twitch-ollama-chatbot/.env
```

Set the following values:

```env
# Twitch Configuration
TWITCH_CLIENT_ID=your_client_id_here
TWITCH_CLIENT_SECRET=your_client_secret_here
TWITCH_CHANNELS=channel1,channel2,channel3

# The bot will automatically detect its username from the OAuth token
```

## Initial Setup

### 1. Configure Ollama

Ensure Ollama is running and has the required model:

```bash
# Check if Ollama is running
curl http://localhost:11434/api/tags

# Pull the default model if not present
ollama pull llama3.1

# Test model
ollama run llama3.1 "Hello, this is a test"
```

### 2. Configure Database (Optional)

For SQLite (default), no additional configuration is needed.

For MySQL:

```bash
# Install MySQL server
sudo apt install mysql-server

# Create database and user
sudo mysql -e "
CREATE DATABASE twitch_bot;
CREATE USER 'chatbot'@'localhost' IDENTIFIED BY 'your_secure_password';
GRANT ALL PRIVILEGES ON twitch_bot.* TO 'chatbot'@'localhost';
FLUSH PRIVILEGES;
"

# Update .env file
sudo nano /opt/twitch-ollama-chatbot/.env
```

Set MySQL configuration in `.env`:

```env
DATABASE_TYPE=mysql
MYSQL_HOST=localhost
MYSQL_PORT=3306
MYSQL_USER=chatbot
MYSQL_PASSWORD=your_secure_password
MYSQL_DATABASE=twitch_bot
```

### 3. Generate Encryption Key (Optional)

For enhanced security, generate an encryption key for token storage:

```bash
python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Add the key to your `.env` file:

```env
TOKEN_ENCRYPTION_KEY=your_generated_key_here
```

### 4. Start the Service

```bash
# Start the service
sudo systemctl start twitch-ollama-chatbot

# Enable auto-start on boot
sudo systemctl enable twitch-ollama-chatbot

# Check status
sudo systemctl status twitch-ollama-chatbot
```

## Verification

### 1. Check Service Status

```bash
# Service status
sudo systemctl status twitch-ollama-chatbot

# View logs
sudo journalctl -u twitch-ollama-chatbot -f

# Check if bot is connected to channels
sudo journalctl -u twitch-ollama-chatbot | grep "Connected to channel"
```

### 2. Test Bot Functionality

1. **Join a channel**: The bot should automatically join configured channels
2. **Send test messages**: Chat in the channel to build up message history
3. **Wait for automatic message**: After the threshold is reached (default: 30 messages), the bot should generate a message
4. **Test mentions**: Try mentioning the bot: `@YourBotName hello`
5. **Test commands**: If you're a moderator, try: `!clank status`

### 3. Monitor Performance

```bash
# Check resource usage
sudo systemctl status twitch-ollama-chatbot

# View detailed logs
sudo journalctl -u twitch-ollama-chatbot --since "1 hour ago"

# Check database size (SQLite)
ls -lh /opt/twitch-ollama-chatbot/data/

# Check log files
ls -lh /opt/twitch-ollama-chatbot/logs/
```

## Troubleshooting

### Common Issues

#### Bot Not Connecting to Twitch

**Symptoms**: Service starts but no channel connections in logs

**Solutions**:
1. Verify OAuth credentials:
   ```bash
   # Test token validity
   curl -H "Authorization: Bearer YOUR_TOKEN" https://id.twitch.tv/oauth2/validate
   ```

2. Check channel names:
   ```bash
   # Ensure channel names are lowercase and without '#'
   TWITCH_CHANNELS=channelname1,channelname2
   ```

3. Verify network connectivity:
   ```bash
   # Test IRC connection
   telnet irc.chat.twitch.tv 6667
   ```

#### Ollama Connection Issues

**Symptoms**: "Ollama unavailable" in logs

**Solutions**:
1. Check Ollama service:
   ```bash
   # Test Ollama API
   curl http://localhost:11434/api/tags
   
   # Check if model exists
   ollama list
   ```

2. Verify Ollama URL in configuration:
   ```env
   OLLAMA_URL=http://localhost:11434
   ```

3. Check firewall settings if Ollama is on a different server

#### Database Connection Issues

**Symptoms**: Database connection errors in logs

**Solutions**:

For SQLite:
```bash
# Check file permissions
ls -la /opt/twitch-ollama-chatbot/data/
sudo chown chatbot:chatbot /opt/twitch-ollama-chatbot/data/chatbot.db
```

For MySQL:
```bash
# Test connection
mysql -h localhost -u chatbot -p twitch_bot

# Check MySQL service
sudo systemctl status mysql
```

#### Permission Issues

**Symptoms**: Permission denied errors

**Solutions**:
```bash
# Fix ownership
sudo chown -R chatbot:chatbot /opt/twitch-ollama-chatbot

# Fix permissions
sudo chmod 755 /opt/twitch-ollama-chatbot
sudo chmod 750 /opt/twitch-ollama-chatbot/data /opt/twitch-ollama-chatbot/logs
sudo chmod 640 /opt/twitch-ollama-chatbot/.env
```

### Getting Help

1. **Check logs first**:
   ```bash
   sudo journalctl -u twitch-ollama-chatbot -f
   ```

2. **Enable debug logging**:
   ```env
   LOG_LEVEL=DEBUG
   ```

3. **Test individual components**:
   ```bash
   # Test database connection
   sudo -u chatbot /opt/twitch-ollama-chatbot/venv/bin/python -c "
   from chatbot.database.operations import DatabaseManager
   import asyncio
   asyncio.run(DatabaseManager().test_connection())
   "
   ```

4. **Check system resources**:
   ```bash
   # Memory usage
   free -h
   
   # Disk space
   df -h
   
   # Process status
   ps aux | grep chatbot
   ```

### Log Locations

- **Systemd logs**: `journalctl -u twitch-ollama-chatbot`
- **Application logs**: `/opt/twitch-ollama-chatbot/logs/chatbot.log`
- **System logs**: `/var/log/syslog`

### Configuration Files

- **Main config**: `/opt/twitch-ollama-chatbot/.env`
- **Service config**: `/etc/systemd/system/twitch-ollama-chatbot.service`
- **Blocked words**: `/opt/twitch-ollama-chatbot/blocked_words.txt`

For additional help, check the [Configuration Reference](CONFIGURATION.md) and [Troubleshooting Guide](TROUBLESHOOTING.md).