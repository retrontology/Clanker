# Deployment Files

This directory contains deployment configurations and scripts for the Twitch Ollama Chatbot.

## Directory Structure

```
deploy/
├── README.md                           # This file
├── install.sh                          # Automated Linux installation script
├── config/                             # Configuration templates
│   ├── production.env                  # Production environment template
│   └── development.env                 # Development environment template
├── docker/                             # Docker deployment files
│   └── docker-compose.production.yml   # Production Docker Compose
├── scripts/                            # Maintenance scripts
│   ├── backup.sh                       # Automated backup script
│   └── update.sh                       # Update script with rollback
└── systemd/                            # Systemd service files
    └── twitch-ollama-chatbot.service   # Linux service configuration
```

## Quick Start

### Automated Linux Installation

For Ubuntu/Debian systems:

```bash
# Clone repository
git clone https://github.com/your-repo/twitch-ollama-chatbot.git
cd twitch-ollama-chatbot

# Run installation script
sudo ./deploy/install.sh
```

This will:
- Create system user and directories
- Install Python dependencies
- Set up systemd service
- Configure log rotation
- Create initial configuration file

### Docker Deployment

For containerized deployment:

```bash
# Development
docker-compose up -d

# Production
docker-compose -f deploy/docker/docker-compose.production.yml up -d
```

## Configuration Templates

### Production Environment

Use `deploy/config/production.env` as a template for production deployments:

```bash
# Copy template
sudo cp deploy/config/production.env /opt/twitch-ollama-chatbot/.env

# Edit configuration
sudo nano /opt/twitch-ollama-chatbot/.env
```

Key production settings:
- MySQL database for better performance
- JSON logging format for log aggregation
- Higher resource thresholds
- Longer message retention
- Token encryption enabled

### Development Environment

Use `deploy/config/development.env` for local development:

```bash
# Copy template
cp deploy/config/development.env .env

# Edit configuration
nano .env
```

Development features:
- SQLite database for simplicity
- Console logging for readability
- Debug log level
- Lower thresholds for faster testing

## Service Management

### Systemd Service

The bot runs as a systemd service on Linux:

```bash
# Service management
sudo systemctl start twitch-ollama-chatbot
sudo systemctl stop twitch-ollama-chatbot
sudo systemctl restart twitch-ollama-chatbot
sudo systemctl status twitch-ollama-chatbot

# Enable/disable auto-start
sudo systemctl enable twitch-ollama-chatbot
sudo systemctl disable twitch-ollama-chatbot

# View logs
sudo journalctl -u twitch-ollama-chatbot -f
```

### Service Configuration

The systemd service file includes:
- Security hardening (sandboxing, restricted permissions)
- Resource limits (memory, CPU)
- Automatic restart on failure
- Proper logging configuration

## Maintenance Scripts

### Backup Script

Automated backup with retention:

```bash
# Run backup manually
sudo /usr/local/bin/chatbot-backup

# Schedule daily backups
echo "0 2 * * * /usr/local/bin/chatbot-backup" | sudo crontab -
```

Features:
- Database backup (SQLite/MySQL)
- Configuration backup (sanitized)
- Log backup (recent files)
- Compressed archives
- Automatic cleanup of old backups

### Update Script

Safe updates with rollback capability:

```bash
# Update to latest version
sudo ./deploy/scripts/update.sh

# Rollback if needed
sudo ./deploy/scripts/update.sh --rollback
```

Update process:
- Creates backup before update
- Stops service safely
- Updates application files
- Updates dependencies
- Runs database migrations
- Starts service and verifies health
- Automatic rollback on failure

## Docker Deployment

### Development Docker

Simple single-container deployment:

```yaml
# docker-compose.yml
services:
  chatbot:
    build: .
    volumes:
      - chatbot_data:/app/data
      - chatbot_logs:/app/logs
    environment:
      - OLLAMA_URL=http://host.docker.internal:11434
```

### Production Docker

Full stack with database and monitoring:

```yaml
# deploy/docker/docker-compose.production.yml
services:
  chatbot:      # Main application
  db:           # MySQL database
  ollama:       # Ollama service
  nginx:        # Reverse proxy (optional)
```

Features:
- Separate database container
- Persistent volumes for data
- Resource limits and health checks
- Network isolation
- Optional GPU support for Ollama

## Security Considerations

### File Permissions

Proper permissions are set automatically:

```bash
# Application directory
/opt/twitch-ollama-chatbot/     # 755 chatbot:chatbot

# Configuration file
.env                            # 640 chatbot:chatbot

# Data directories
data/                           # 750 chatbot:chatbot
logs/                           # 750 chatbot:chatbot

# Database file
data/chatbot.db                 # 640 chatbot:chatbot
```

### Systemd Security

The service runs with security hardening:
- Non-root user execution
- Restricted filesystem access
- No new privileges
- Private temporary directory
- Protected system directories
- Limited system calls

### Network Security

Recommendations:
- Run Ollama on localhost when possible
- Use firewall rules to restrict access
- Consider VPN for remote Ollama servers
- Monitor network traffic

## Troubleshooting

### Installation Issues

Common problems and solutions:

**Permission denied**:
```bash
# Fix ownership
sudo chown -R chatbot:chatbot /opt/twitch-ollama-chatbot
```

**Service won't start**:
```bash
# Check service status
sudo systemctl status twitch-ollama-chatbot -l

# Check logs
sudo journalctl -u twitch-ollama-chatbot --since "1 hour ago"
```

**Database connection failed**:
```bash
# Test database connection
sudo -u chatbot /opt/twitch-ollama-chatbot/venv/bin/python -c "
from chatbot.database.operations import DatabaseManager
import asyncio
asyncio.run(DatabaseManager().test_connection())
"
```

### Docker Issues

**Container won't start**:
```bash
# Check container logs
docker-compose logs chatbot

# Check resource usage
docker stats
```

**Ollama connection failed**:
```bash
# Test Ollama connectivity from container
docker-compose exec chatbot curl http://host.docker.internal:11434/api/tags
```

### Performance Issues

**High memory usage**:
- Reduce context window size
- Increase cleanup frequency
- Lower message retention period

**Slow responses**:
- Check Ollama performance
- Optimize database queries
- Consider hardware upgrade

## Monitoring

### Health Checks

Built-in health monitoring:
- Service status monitoring
- Resource usage tracking
- Database connectivity checks
- Ollama API availability

### Log Analysis

Important log patterns to monitor:
- Connection failures
- Authentication errors
- Database errors
- High resource usage
- Content filter blocks

### Performance Metrics

Key metrics to track:
- Message generation success rate
- Response times (Ollama, database)
- Memory and CPU usage
- Error rates by type
- Channel activity levels

## Support

For deployment issues:

1. Check the [Troubleshooting Guide](../docs/TROUBLESHOOTING.md)
2. Review service logs: `sudo journalctl -u twitch-ollama-chatbot -f`
3. Verify configuration: Check `.env` file settings
4. Test components individually: Database, Ollama, network connectivity
5. Report issues with full diagnostic information

## Contributing

When adding new deployment features:

1. Update relevant documentation
2. Test on clean systems
3. Consider security implications
4. Add appropriate error handling
5. Update this README if needed