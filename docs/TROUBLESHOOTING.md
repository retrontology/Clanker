# Troubleshooting Guide - Twitch Ollama Chatbot

This guide helps you diagnose and resolve common issues with the Twitch Ollama Chatbot.

## Table of Contents

- [Quick Diagnostics](#quick-diagnostics)
- [Connection Issues](#connection-issues)
- [Authentication Problems](#authentication-problems)
- [Database Issues](#database-issues)
- [Ollama Integration Problems](#ollama-integration-problems)
- [Performance Issues](#performance-issues)
- [Content Filtering Issues](#content-filtering-issues)
- [Configuration Problems](#configuration-problems)
- [Service Management Issues](#service-management-issues)
- [Log Analysis](#log-analysis)
- [Recovery Procedures](#recovery-procedures)

## Quick Diagnostics

### Health Check Commands

Run these commands to quickly assess bot health:

```bash
# Service status
sudo systemctl status twitch-ollama-chatbot

# Recent logs
sudo journalctl -u twitch-ollama-chatbot --since "10 minutes ago"

# Resource usage
ps aux | grep chatbot
free -h
df -h

# Network connectivity
curl -s http://localhost:11434/api/tags | head -5
```

### Common Status Indicators

**Healthy Bot**:
- Service status: `active (running)`
- Logs show: "Connected to channel: channelname"
- No error messages in recent logs
- Ollama API responds to curl test

**Unhealthy Bot**:
- Service status: `failed` or `inactive`
- Logs show connection errors or exceptions
- High memory usage or disk space issues
- Ollama API not responding

## Connection Issues

### Bot Not Connecting to Twitch IRC

**Symptoms**:
- Service starts but no "Connected to channel" messages
- "Connection failed" or "Authentication failed" in logs
- Bot doesn't appear in channel user list

**Diagnostic Steps**:

1. **Check OAuth token validity**:
   ```bash
   # Test token (replace YOUR_TOKEN with actual token)
   curl -H "Authorization: Bearer YOUR_TOKEN" \
        https://id.twitch.tv/oauth2/validate
   ```

2. **Verify channel configuration**:
   ```bash
   # Check channel names in config
   grep TWITCH_CHANNELS /opt/twitch-ollama-chatbot/.env
   
   # Ensure channels are lowercase, no # prefix
   # Correct: TWITCH_CHANNELS=channelname1,channelname2
   # Wrong: TWITCH_CHANNELS=#ChannelName1,#ChannelName2
   ```

3. **Test network connectivity**:
   ```bash
   # Test IRC server connectivity
   telnet irc.chat.twitch.tv 6667
   
   # Test DNS resolution
   nslookup irc.chat.twitch.tv
   ```

**Solutions**:

- **Invalid token**: Generate new OAuth token
- **Wrong channel names**: Fix channel names in configuration
- **Network issues**: Check firewall, proxy settings
- **Rate limiting**: Wait and retry, check for multiple bot instances

### Frequent Disconnections

**Symptoms**:
- Bot connects but disconnects frequently
- "Reconnecting..." messages in logs
- Inconsistent bot presence in channels

**Diagnostic Steps**:

1. **Check network stability**:
   ```bash
   # Monitor network connectivity
   ping -c 10 irc.chat.twitch.tv
   
   # Check for packet loss
   mtr irc.chat.twitch.tv
   ```

2. **Review reconnection logs**:
   ```bash
   # Look for reconnection patterns
   sudo journalctl -u twitch-ollama-chatbot | grep -i "reconnect\|disconnect"
   ```

**Solutions**:

- **Network instability**: Improve network connection, use wired connection
- **ISP issues**: Contact ISP, consider VPN
- **Server overload**: Reduce resource usage, upgrade hardware
- **Multiple instances**: Ensure only one bot instance is running

## Authentication Problems

### OAuth Token Issues

**Symptoms**:
- "Authentication failed" in logs
- "Invalid token" errors
- Bot can't join channels despite correct configuration

**Diagnostic Steps**:

1. **Validate token**:
   ```bash
   # Check token validity and scopes
   curl -H "Authorization: Bearer YOUR_TOKEN" \
        https://id.twitch.tv/oauth2/validate
   ```

2. **Check token scopes**:
   Required scopes: `chat:read`, `chat:edit`

3. **Verify client credentials**:
   ```bash
   # Check if client ID and secret are correct
   grep TWITCH_CLIENT /opt/twitch-ollama-chatbot/.env
   ```

**Solutions**:

- **Expired token**: Generate new OAuth token
- **Wrong scopes**: Regenerate token with correct scopes
- **Invalid credentials**: Verify client ID and secret from Twitch Developer Console
- **Token corruption**: Clear stored tokens and re-authenticate

### Username Detection Issues

**Symptoms**:
- Bot connects but doesn't know its own username
- "Unable to detect bot username" in logs
- Bot responds to its own messages

**Diagnostic Steps**:

1. **Check OAuth response**:
   ```bash
   # Look for username detection in logs
   sudo journalctl -u twitch-ollama-chatbot | grep -i "username\|detected"
   ```

2. **Verify token user**:
   ```bash
   # Check which user the token belongs to
   curl -H "Authorization: Bearer YOUR_TOKEN" \
        https://api.twitch.tv/helix/users \
        -H "Client-Id: YOUR_CLIENT_ID"
   ```

**Solutions**:

- **Token mismatch**: Ensure token belongs to bot account
- **API changes**: Update bot to handle API response changes
- **Manual override**: Set bot username manually in configuration

## Database Issues

### SQLite Problems

**Symptoms**:
- "Database locked" errors
- "Permission denied" when accessing database
- Corrupted database messages

**Diagnostic Steps**:

1. **Check file permissions**:
   ```bash
   ls -la /opt/twitch-ollama-chatbot/data/
   
   # Should show:
   # -rw-r----- chatbot chatbot chatbot.db
   ```

2. **Test database integrity**:
   ```bash
   # Check database integrity
   sudo -u chatbot sqlite3 /opt/twitch-ollama-chatbot/data/chatbot.db \
        "PRAGMA integrity_check;"
   ```

3. **Check disk space**:
   ```bash
   df -h /opt/twitch-ollama-chatbot/data/
   ```

**Solutions**:

- **Permission issues**: Fix file ownership and permissions
- **Disk full**: Clean up old files, increase disk space
- **Database corruption**: Restore from backup or recreate database
- **Lock issues**: Ensure only one bot instance is running

### MySQL Problems

**Symptoms**:
- "Connection refused" to MySQL
- "Access denied" for database user
- "Table doesn't exist" errors

**Diagnostic Steps**:

1. **Test MySQL connection**:
   ```bash
   # Test connection with bot credentials
   mysql -h localhost -u chatbot -p twitch_bot
   ```

2. **Check MySQL service**:
   ```bash
   sudo systemctl status mysql
   ```

3. **Verify database and tables**:
   ```sql
   -- In MySQL console
   SHOW DATABASES;
   USE twitch_bot;
   SHOW TABLES;
   ```

**Solutions**:

- **Service down**: Start MySQL service
- **Wrong credentials**: Verify username/password in configuration
- **Missing database**: Create database and run migrations
- **Network issues**: Check MySQL bind address and firewall

## Ollama Integration Problems

### Ollama Server Unreachable

**Symptoms**:
- "Ollama unavailable" in logs
- Bot connects but never generates messages
- Timeout errors when generating responses

**Diagnostic Steps**:

1. **Test Ollama API**:
   ```bash
   # Test basic connectivity
   curl http://localhost:11434/api/tags
   
   # Test model availability
   curl http://localhost:11434/api/show -d '{"name":"llama3.1"}'
   ```

2. **Check Ollama service**:
   ```bash
   # If Ollama is running as a service
   sudo systemctl status ollama
   
   # Check Ollama process
   ps aux | grep ollama
   ```

3. **Verify model installation**:
   ```bash
   ollama list
   ```

**Solutions**:

- **Service down**: Start Ollama service
- **Wrong URL**: Verify `OLLAMA_URL` in configuration
- **Missing model**: Install required model with `ollama pull`
- **Network issues**: Check firewall, proxy settings
- **Resource limits**: Ensure sufficient RAM/GPU for model

### Model Loading Issues

**Symptoms**:
- "Model not found" errors
- Slow response times
- Out of memory errors

**Diagnostic Steps**:

1. **Check available models**:
   ```bash
   ollama list
   ```

2. **Test model directly**:
   ```bash
   ollama run llama3.1 "Test message"
   ```

3. **Monitor resource usage**:
   ```bash
   # Check memory usage during model loading
   htop
   
   # Check GPU usage (if applicable)
   nvidia-smi
   ```

**Solutions**:

- **Missing model**: Install with `ollama pull model_name`
- **Insufficient memory**: Use smaller model or add more RAM
- **GPU issues**: Check CUDA installation, GPU drivers
- **Model corruption**: Reinstall model

## Performance Issues

### High Memory Usage

**Symptoms**:
- Bot process using excessive RAM
- System becomes slow or unresponsive
- Out of memory errors

**Diagnostic Steps**:

1. **Monitor memory usage**:
   ```bash
   # Check bot memory usage
   ps aux | grep chatbot
   
   # Monitor over time
   top -p $(pgrep -f chatbot)
   ```

2. **Check memory leaks**:
   ```bash
   # Look for memory-related errors
   sudo journalctl -u twitch-ollama-chatbot | grep -i "memory\|oom"
   ```

**Solutions**:

- **Reduce context window**: Lower `DEFAULT_CONTEXT_LIMIT`
- **Increase cleanup frequency**: Lower `CLEANUP_INTERVAL_MINUTES`
- **Reduce retention**: Lower `MESSAGE_RETENTION_DAYS`
- **Add more RAM**: Upgrade system memory
- **Restart service**: Temporary fix for memory leaks

### Slow Response Times

**Symptoms**:
- Long delays between trigger and message generation
- Timeout errors in logs
- Users complaining about slow bot responses

**Diagnostic Steps**:

1. **Check Ollama performance**:
   ```bash
   # Time a direct Ollama request
   time curl -X POST http://localhost:11434/api/generate \
        -d '{"model":"llama3.1","prompt":"Hello","stream":false}'
   ```

2. **Monitor database performance**:
   ```bash
   # Check database query times in logs
   sudo journalctl -u twitch-ollama-chatbot | grep -i "query\|database"
   ```

**Solutions**:

- **Optimize database**: Add indexes, clean old data
- **Reduce context size**: Lower context window
- **Upgrade hardware**: Faster CPU, more RAM, SSD storage
- **Use smaller model**: Switch to faster Ollama model
- **Increase timeout**: Raise `OLLAMA_TIMEOUT` value

### High CPU Usage

**Symptoms**:
- Bot process consuming high CPU
- System becomes sluggish
- Thermal throttling on servers

**Diagnostic Steps**:

1. **Monitor CPU usage**:
   ```bash
   # Check CPU usage by process
   htop
   
   # Monitor bot specifically
   top -p $(pgrep -f chatbot)
   ```

2. **Profile bot activity**:
   ```bash
   # Check what the bot is doing
   sudo strace -p $(pgrep -f chatbot) -c
   ```

**Solutions**:

- **Reduce processing frequency**: Increase cooldowns
- **Optimize content filtering**: Use more efficient filters
- **Database optimization**: Add indexes, optimize queries
- **Limit concurrent operations**: Reduce parallel processing

## Content Filtering Issues

### Messages Not Being Filtered

**Symptoms**:
- Inappropriate content appears in bot messages
- Bot learns from blocked content
- Filter warnings not appearing in logs

**Diagnostic Steps**:

1. **Check filter configuration**:
   ```bash
   # Verify filter is enabled
   grep CONTENT_FILTER_ENABLED /opt/twitch-ollama-chatbot/.env
   
   # Check blocked words file
   head -10 /opt/twitch-ollama-chatbot/blocked_words.txt
   ```

2. **Test filter manually**:
   ```bash
   # Test filter with known bad content
   sudo -u chatbot /opt/twitch-ollama-chatbot/venv/bin/python -c "
   from chatbot.processing.filters import ContentFilter
   filter = ContentFilter('/opt/twitch-ollama-chatbot/blocked_words.txt')
   print(filter.filter_input('test bad word'))
   "
   ```

**Solutions**:

- **Enable filtering**: Set `CONTENT_FILTER_ENABLED=true`
- **Update blocked words**: Add missing terms to blocked words file
- **Fix file path**: Verify `BLOCKED_WORDS_FILE` path is correct
- **Restart service**: Reload configuration after changes

### Over-Aggressive Filtering

**Symptoms**:
- Bot rarely generates messages
- Many false positives in filter logs
- Legitimate content being blocked

**Diagnostic Steps**:

1. **Review filter logs**:
   ```bash
   # Check what's being blocked
   sudo journalctl -u twitch-ollama-chatbot | grep -i "blocked\|filter"
   ```

2. **Analyze blocked words list**:
   ```bash
   # Review blocked words for overly broad terms
   cat /opt/twitch-ollama-chatbot/blocked_words.txt
   ```

**Solutions**:

- **Refine blocked words**: Remove overly broad terms
- **Adjust normalization**: Modify text normalization rules
- **Whitelist exceptions**: Add exception handling for false positives
- **Tune sensitivity**: Adjust filtering algorithms

## Configuration Problems

### Environment Variable Issues

**Symptoms**:
- Bot uses default values instead of configured ones
- "Configuration not found" errors
- Settings don't take effect after changes

**Diagnostic Steps**:

1. **Check environment file**:
   ```bash
   # Verify .env file exists and is readable
   ls -la /opt/twitch-ollama-chatbot/.env
   
   # Check file contents
   sudo cat /opt/twitch-ollama-chatbot/.env
   ```

2. **Test environment loading**:
   ```bash
   # Check if variables are loaded
   sudo -u chatbot /opt/twitch-ollama-chatbot/venv/bin/python -c "
   import os
   from dotenv import load_dotenv
   load_dotenv('/opt/twitch-ollama-chatbot/.env')
   print('OLLAMA_URL:', os.getenv('OLLAMA_URL'))
   "
   ```

**Solutions**:

- **Fix file permissions**: Ensure chatbot user can read .env file
- **Fix syntax errors**: Check for missing quotes, invalid characters
- **Restart service**: Environment changes require restart
- **Check file encoding**: Ensure UTF-8 encoding

### Chat Command Issues

**Symptoms**:
- Commands don't respond or give errors
- "Permission denied" for moderators
- Settings don't persist after restart

**Diagnostic Steps**:

1. **Test command permissions**:
   ```bash
   # Check user badges in logs
   sudo journalctl -u twitch-ollama-chatbot | grep -i "badge\|command"
   ```

2. **Verify database persistence**:
   ```bash
   # Check if settings are saved to database
   sudo -u chatbot sqlite3 /opt/twitch-ollama-chatbot/data/chatbot.db \
        "SELECT * FROM channel_config;"
   ```

**Solutions**:

- **Check user permissions**: Verify user has moderator/broadcaster badge
- **Database issues**: Fix database connectivity problems
- **Command parsing**: Check for typos in command syntax
- **Restart service**: Reload command handlers

## Service Management Issues

### Service Won't Start

**Symptoms**:
- `systemctl start` fails
- Service status shows "failed"
- Immediate exit after start attempt

**Diagnostic Steps**:

1. **Check service status**:
   ```bash
   sudo systemctl status twitch-ollama-chatbot -l
   ```

2. **Check service logs**:
   ```bash
   sudo journalctl -u twitch-ollama-chatbot --since "1 hour ago"
   ```

3. **Test manual start**:
   ```bash
   # Try running manually to see errors
   sudo -u chatbot /opt/twitch-ollama-chatbot/venv/bin/python -m chatbot.main
   ```

**Solutions**:

- **Fix configuration errors**: Correct invalid settings
- **Install missing dependencies**: Run pip install
- **Fix permissions**: Correct file ownership and permissions
- **Check Python path**: Verify virtual environment is correct

### Service Keeps Restarting

**Symptoms**:
- Service status shows frequent restarts
- "Start request repeated too quickly" errors
- Bot appears and disappears from channels

**Diagnostic Steps**:

1. **Check restart frequency**:
   ```bash
   # Look for restart patterns
   sudo journalctl -u twitch-ollama-chatbot | grep -i "start\|stop\|restart"
   ```

2. **Identify crash cause**:
   ```bash
   # Look for error messages before restarts
   sudo journalctl -u twitch-ollama-chatbot | grep -B5 -A5 "exit\|crash\|error"
   ```

**Solutions**:

- **Fix underlying errors**: Address root cause of crashes
- **Increase restart delay**: Modify systemd service RestartSec
- **Add health checks**: Implement better error handling
- **Resource limits**: Ensure adequate system resources

## Log Analysis

### Understanding Log Levels

**DEBUG**: Detailed information for development
**INFO**: General operational messages
**WARNING**: Potential issues that don't stop operation
**ERROR**: Serious problems that may cause failures

### Key Log Patterns

**Successful startup**:
```
INFO Bot started successfully
INFO Connected to channel: channelname
INFO Ollama client initialized
```

**Connection issues**:
```
ERROR Failed to connect to Twitch IRC
WARNING Reconnection attempt 1/3
ERROR Authentication failed
```

**Generation issues**:
```
WARNING Ollama request timeout
ERROR Content filter blocked message
INFO Generated spontaneous message
```

### Log Analysis Commands

```bash
# Recent errors only
sudo journalctl -u twitch-ollama-chatbot -p err --since "1 hour ago"

# Follow logs in real-time
sudo journalctl -u twitch-ollama-chatbot -f

# Search for specific patterns
sudo journalctl -u twitch-ollama-chatbot | grep -i "pattern"

# Export logs for analysis
sudo journalctl -u twitch-ollama-chatbot --since "1 day ago" > bot_logs.txt
```

## Recovery Procedures

### Emergency Stop

```bash
# Stop service immediately
sudo systemctl stop twitch-ollama-chatbot

# Disable auto-restart
sudo systemctl disable twitch-ollama-chatbot

# Kill any remaining processes
sudo pkill -f chatbot
```

### Configuration Reset

```bash
# Backup current config
sudo cp /opt/twitch-ollama-chatbot/.env /opt/twitch-ollama-chatbot/.env.backup

# Reset to defaults
sudo cp /opt/twitch-ollama-chatbot/.env.example /opt/twitch-ollama-chatbot/.env

# Edit with correct values
sudo nano /opt/twitch-ollama-chatbot/.env
```

### Database Recovery

**SQLite**:
```bash
# Backup corrupted database
sudo cp /opt/twitch-ollama-chatbot/data/chatbot.db /tmp/chatbot.db.corrupted

# Restore from backup
sudo cp /var/backups/twitch-ollama-chatbot/latest_backup.db \
       /opt/twitch-ollama-chatbot/data/chatbot.db

# Or recreate empty database
sudo rm /opt/twitch-ollama-chatbot/data/chatbot.db
sudo systemctl start twitch-ollama-chatbot
```

**MySQL**:
```bash
# Restore from backup
mysql -u chatbot -p twitch_bot < /var/backups/twitch-ollama-chatbot/latest_backup.sql
```

### Complete Reinstallation

```bash
# Stop and disable service
sudo systemctl stop twitch-ollama-chatbot
sudo systemctl disable twitch-ollama-chatbot

# Backup data
sudo cp -r /opt/twitch-ollama-chatbot/data /tmp/chatbot_data_backup
sudo cp /opt/twitch-ollama-chatbot/.env /tmp/chatbot_env_backup

# Remove installation
sudo rm -rf /opt/twitch-ollama-chatbot
sudo rm /etc/systemd/system/twitch-ollama-chatbot.service

# Reinstall
./deploy/install.sh

# Restore data
sudo cp -r /tmp/chatbot_data_backup/* /opt/twitch-ollama-chatbot/data/
sudo cp /tmp/chatbot_env_backup /opt/twitch-ollama-chatbot/.env
sudo chown -R chatbot:chatbot /opt/twitch-ollama-chatbot
```

### Getting Additional Help

1. **Enable debug logging**:
   ```env
   LOG_LEVEL=DEBUG
   ```

2. **Collect diagnostic information**:
   ```bash
   # System info
   uname -a
   python3 --version
   free -h
   df -h
   
   # Service info
   sudo systemctl status twitch-ollama-chatbot
   sudo journalctl -u twitch-ollama-chatbot --since "1 hour ago"
   
   # Configuration
   sudo cat /opt/twitch-ollama-chatbot/.env | grep -v -E "(PASSWORD|SECRET|KEY)"
   ```

3. **Test individual components**:
   ```bash
   # Test Ollama
   curl http://localhost:11434/api/tags
   
   # Test database
   sudo -u chatbot sqlite3 /opt/twitch-ollama-chatbot/data/chatbot.db ".tables"
   
   # Test Python environment
   sudo -u chatbot /opt/twitch-ollama-chatbot/venv/bin/python -c "import chatbot; print('OK')"
   ```

For additional support, provide this diagnostic information along with your specific issue description.