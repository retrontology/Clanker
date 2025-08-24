# Deployment Guide - Twitch Ollama Chatbot

This guide covers different deployment scenarios for the Twitch Ollama Chatbot, from development setups to production environments.

## Table of Contents

- [Deployment Overview](#deployment-overview)
- [Development Deployment](#development-deployment)
- [Production Deployment](#production-deployment)
- [Docker Deployment](#docker-deployment)
- [Cloud Deployment](#cloud-deployment)
- [Scaling Considerations](#scaling-considerations)
- [Backup and Recovery](#backup-and-recovery)
- [Monitoring and Maintenance](#monitoring-and-maintenance)

## Deployment Overview

### Deployment Options

1. **Development**: Local development with minimal setup
2. **Single Server**: Traditional Linux server deployment
3. **Docker**: Containerized deployment with Docker Compose
4. **Cloud**: Cloud platform deployment (AWS, GCP, Azure)
5. **Kubernetes**: Container orchestration for large-scale deployments

### Architecture Components

- **Application**: Python chatbot application
- **Database**: SQLite (development) or MySQL (production)
- **Ollama**: Local LLM server
- **Reverse Proxy**: Nginx (optional, for monitoring endpoints)
- **Monitoring**: Logs, metrics, and health checks

## Development Deployment

### Local Development Setup

**Prerequisites**:
- Python 3.11+
- Ollama installed locally
- Git

**Quick Setup**:

```bash
# Clone repository
git clone https://github.com/your-repo/twitch-ollama-chatbot.git
cd twitch-ollama-chatbot

# Create virtual environment
python3 -m venv venv
source venv/bin/activate  # Linux/Mac
# or
venv\Scripts\activate     # Windows

# Install dependencies
pip install -r requirements.txt
pip install -e .

# Configure environment
cp .env.example .env
nano .env  # Edit with your settings

# Start Ollama (if not running)
ollama serve &
ollama pull llama3.1

# Run the bot
python -m chatbot.main
```

**Development Configuration**:

```env
# .env for development
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

### Development Best Practices

- Use a dedicated test Twitch channel
- Enable debug logging for detailed output
- Use lower thresholds for faster testing
- Keep database file in project directory
- Use console log format for readability

## Production Deployment

### Linux Server Deployment

**System Requirements**:
- Ubuntu 20.04+ or equivalent Linux distribution
- 2GB RAM minimum (4GB recommended)
- 10GB disk space minimum
- Python 3.11+
- Systemd for service management

**Automated Installation**:

```bash
# Clone repository
git clone https://github.com/your-repo/twitch-ollama-chatbot.git
cd twitch-ollama-chatbot

# Run installation script
sudo ./deploy/install.sh
```

**Manual Installation Steps**:

1. **Create system user**:
   ```bash
   sudo groupadd --system chatbot
   sudo useradd --system --gid chatbot --home-dir /opt/twitch-ollama-chatbot \
                --shell /bin/false --comment "Twitch Ollama Chatbot" chatbot
   ```

2. **Install application**:
   ```bash
   sudo mkdir -p /opt/twitch-ollama-chatbot/{data,logs}
   sudo cp -r chatbot/ requirements.txt setup.py blocked_words.txt /opt/twitch-ollama-chatbot/
   sudo chown -R chatbot:chatbot /opt/twitch-ollama-chatbot
   ```

3. **Create virtual environment**:
   ```bash
   sudo -u chatbot python3 -m venv /opt/twitch-ollama-chatbot/venv
   sudo -u chatbot /opt/twitch-ollama-chatbot/venv/bin/pip install -r /opt/twitch-ollama-chatbot/requirements.txt
   sudo -u chatbot /opt/twitch-ollama-chatbot/venv/bin/pip install -e /opt/twitch-ollama-chatbot
   ```

4. **Install systemd service**:
   ```bash
   sudo cp deploy/systemd/twitch-ollama-chatbot.service /etc/systemd/system/
   sudo systemctl daemon-reload
   sudo systemctl enable twitch-ollama-chatbot
   ```

5. **Configure application**:
   ```bash
   sudo cp deploy/config/production.env /opt/twitch-ollama-chatbot/.env
   sudo nano /opt/twitch-ollama-chatbot/.env  # Configure settings
   sudo chmod 640 /opt/twitch-ollama-chatbot/.env
   ```

**Production Configuration**:

```env
# Production .env
DATABASE_TYPE=mysql
MYSQL_HOST=localhost
MYSQL_USER=chatbot
MYSQL_PASSWORD=secure_password
MYSQL_DATABASE=twitch_bot

OLLAMA_URL=http://localhost:11434
OLLAMA_MODEL=llama3.1
OLLAMA_TIMEOUT=30

TWITCH_CLIENT_ID=your_client_id
TWITCH_CLIENT_SECRET=your_client_secret
TWITCH_CHANNELS=channel1,channel2,channel3
TOKEN_ENCRYPTION_KEY=generated_key_here

LOG_LEVEL=INFO
LOG_FORMAT=json
LOG_FILE=/opt/twitch-ollama-chatbot/logs/chatbot.log

MEMORY_WARNING_MB=1024
MEMORY_CRITICAL_MB=2048
MESSAGE_RETENTION_DAYS=90
METRICS_RETENTION_DAYS=30
```

### MySQL Setup for Production

```bash
# Install MySQL
sudo apt update
sudo apt install mysql-server

# Secure installation
sudo mysql_secure_installation

# Create database and user
sudo mysql -e "
CREATE DATABASE twitch_bot CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'chatbot'@'localhost' IDENTIFIED BY 'secure_password';
GRANT ALL PRIVILEGES ON twitch_bot.* TO 'chatbot'@'localhost';
FLUSH PRIVILEGES;
"
```

### Service Management

```bash
# Start service
sudo systemctl start twitch-ollama-chatbot

# Check status
sudo systemctl status twitch-ollama-chatbot

# View logs
sudo journalctl -u twitch-ollama-chatbot -f

# Stop service
sudo systemctl stop twitch-ollama-chatbot

# Restart service
sudo systemctl restart twitch-ollama-chatbot
```

## Docker Deployment

### Simple Docker Deployment

**Docker Compose Setup**:

```bash
# Clone repository
git clone https://github.com/your-repo/twitch-ollama-chatbot.git
cd twitch-ollama-chatbot

# Configure environment
cp .env.example .env
nano .env  # Configure your settings

# Start services
docker-compose up -d

# View logs
docker-compose logs -f chatbot

# Stop services
docker-compose down
```

### Production Docker Deployment

**Full Stack with MySQL and Ollama**:

```bash
# Use production compose file
docker-compose -f deploy/docker/docker-compose.production.yml up -d

# Check services
docker-compose -f deploy/docker/docker-compose.production.yml ps

# View logs
docker-compose -f deploy/docker/docker-compose.production.yml logs -f chatbot
```

**Production Docker Environment**:

```env
# .env for Docker production
TWITCH_CLIENT_ID=your_client_id
TWITCH_CLIENT_SECRET=your_client_secret
TWITCH_CHANNELS=channel1,channel2,channel3
TOKEN_ENCRYPTION_KEY=generated_key_here
MYSQL_PASSWORD=secure_mysql_password
MYSQL_ROOT_PASSWORD=secure_root_password
```

### Docker Management Commands

```bash
# Update application
docker-compose pull
docker-compose up -d

# Backup data
docker run --rm -v chatbot_data:/data -v $(pwd):/backup alpine \
    tar czf /backup/chatbot_data_backup.tar.gz -C /data .

# Restore data
docker run --rm -v chatbot_data:/data -v $(pwd):/backup alpine \
    tar xzf /backup/chatbot_data_backup.tar.gz -C /data

# Access container shell
docker-compose exec chatbot bash

# View resource usage
docker stats
```

## Cloud Deployment

### AWS Deployment

**EC2 Instance Setup**:

1. **Launch EC2 instance**:
   - Instance type: t3.medium or larger
   - OS: Ubuntu 20.04 LTS
   - Storage: 20GB GP3
   - Security group: SSH (22), HTTP (80), HTTPS (443)

2. **Install dependencies**:
   ```bash
   # Connect to instance
   ssh -i your-key.pem ubuntu@your-instance-ip
   
   # Update system
   sudo apt update && sudo apt upgrade -y
   
   # Install Docker
   curl -fsSL https://get.docker.com -o get-docker.sh
   sudo sh get-docker.sh
   sudo usermod -aG docker ubuntu
   
   # Install Docker Compose
   sudo curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
   sudo chmod +x /usr/local/bin/docker-compose
   ```

3. **Deploy application**:
   ```bash
   # Clone and configure
   git clone https://github.com/your-repo/twitch-ollama-chatbot.git
   cd twitch-ollama-chatbot
   cp .env.example .env
   nano .env  # Configure settings
   
   # Start services
   docker-compose -f deploy/docker/docker-compose.production.yml up -d
   ```

**RDS Database (Optional)**:

```bash
# Create RDS MySQL instance
aws rds create-db-instance \
    --db-instance-identifier twitch-chatbot-db \
    --db-instance-class db.t3.micro \
    --engine mysql \
    --master-username admin \
    --master-user-password secure_password \
    --allocated-storage 20 \
    --vpc-security-group-ids sg-your-security-group

# Update .env with RDS endpoint
MYSQL_HOST=twitch-chatbot-db.region.rds.amazonaws.com
```

### Google Cloud Platform

**Compute Engine Setup**:

```bash
# Create instance
gcloud compute instances create twitch-chatbot \
    --image-family=ubuntu-2004-lts \
    --image-project=ubuntu-os-cloud \
    --machine-type=e2-medium \
    --boot-disk-size=20GB \
    --tags=http-server,https-server

# SSH to instance
gcloud compute ssh twitch-chatbot

# Follow standard Linux deployment steps
```

### Azure Deployment

**Virtual Machine Setup**:

```bash
# Create resource group
az group create --name twitch-chatbot-rg --location eastus

# Create VM
az vm create \
    --resource-group twitch-chatbot-rg \
    --name twitch-chatbot-vm \
    --image UbuntuLTS \
    --size Standard_B2s \
    --admin-username azureuser \
    --generate-ssh-keys

# SSH to VM
az vm show --resource-group twitch-chatbot-rg --name twitch-chatbot-vm -d --query publicIps -o tsv
ssh azureuser@public-ip

# Follow standard Linux deployment steps
```

## Scaling Considerations

### Single Channel vs Multi-Channel

**Single Channel Deployment**:
- Minimal resources required
- Simple configuration
- SQLite database sufficient
- 1GB RAM, 1 CPU core

**Multi-Channel Deployment**:
- More resources needed
- MySQL recommended
- Consider load balancing
- 2-4GB RAM, 2+ CPU cores

### Performance Optimization

**Database Optimization**:
```sql
-- MySQL optimization
SET GLOBAL innodb_buffer_pool_size = 256M;
SET GLOBAL query_cache_size = 64M;
SET GLOBAL max_connections = 100;

-- Add indexes for performance
CREATE INDEX idx_messages_channel_timestamp ON messages(channel, timestamp);
CREATE INDEX idx_channel_config_channel ON channel_config(channel);
```

**Application Tuning**:
```env
# High-performance settings
DEFAULT_CONTEXT_LIMIT=150
CLEANUP_INTERVAL_MINUTES=15
MESSAGE_RETENTION_DAYS=60
OLLAMA_TIMEOUT=20
```

### Load Balancing

For very high-traffic deployments:

```yaml
# docker-compose.scale.yml
version: '3.8'
services:
  chatbot:
    deploy:
      replicas: 3
    environment:
      - INSTANCE_ID=${HOSTNAME}
  
  nginx:
    image: nginx:alpine
    ports:
      - "80:80"
    volumes:
      - ./nginx.conf:/etc/nginx/nginx.conf
```

## Backup and Recovery

### Automated Backup Script

```bash
# Install backup script
sudo cp deploy/scripts/backup.sh /usr/local/bin/chatbot-backup
sudo chmod +x /usr/local/bin/chatbot-backup

# Create cron job for daily backups
echo "0 2 * * * /usr/local/bin/chatbot-backup" | sudo crontab -
```

### Manual Backup Procedures

**SQLite Backup**:
```bash
# Stop service
sudo systemctl stop twitch-ollama-chatbot

# Backup database
sudo cp /opt/twitch-ollama-chatbot/data/chatbot.db /backup/chatbot_$(date +%Y%m%d).db

# Backup configuration
sudo cp /opt/twitch-ollama-chatbot/.env /backup/chatbot_env_$(date +%Y%m%d)

# Start service
sudo systemctl start twitch-ollama-chatbot
```

**MySQL Backup**:
```bash
# Backup database
mysqldump -u chatbot -p twitch_bot > /backup/chatbot_mysql_$(date +%Y%m%d).sql

# Restore database
mysql -u chatbot -p twitch_bot < /backup/chatbot_mysql_20240115.sql
```

### Disaster Recovery

**Complete System Recovery**:

1. **Prepare new system**:
   ```bash
   # Install base system
   sudo ./deploy/install.sh
   ```

2. **Restore configuration**:
   ```bash
   # Restore environment file
   sudo cp /backup/chatbot_env_latest /opt/twitch-ollama-chatbot/.env
   sudo chown chatbot:chatbot /opt/twitch-ollama-chatbot/.env
   sudo chmod 640 /opt/twitch-ollama-chatbot/.env
   ```

3. **Restore database**:
   ```bash
   # SQLite
   sudo cp /backup/chatbot_latest.db /opt/twitch-ollama-chatbot/data/chatbot.db
   sudo chown chatbot:chatbot /opt/twitch-ollama-chatbot/data/chatbot.db
   
   # MySQL
   mysql -u chatbot -p twitch_bot < /backup/chatbot_mysql_latest.sql
   ```

4. **Start services**:
   ```bash
   sudo systemctl start twitch-ollama-chatbot
   sudo systemctl status twitch-ollama-chatbot
   ```

## Monitoring and Maintenance

### Health Monitoring

**System Health Checks**:
```bash
#!/bin/bash
# health-check.sh

# Check service status
if ! systemctl is-active --quiet twitch-ollama-chatbot; then
    echo "CRITICAL: Service is not running"
    exit 2
fi

# Check memory usage
MEMORY_USAGE=$(ps -o pid,ppid,cmd,%mem --sort=-%mem | grep chatbot | head -1 | awk '{print $4}')
if (( $(echo "$MEMORY_USAGE > 80" | bc -l) )); then
    echo "WARNING: High memory usage: ${MEMORY_USAGE}%"
fi

# Check disk space
DISK_USAGE=$(df /opt/twitch-ollama-chatbot | tail -1 | awk '{print $5}' | sed 's/%//')
if [ "$DISK_USAGE" -gt 85 ]; then
    echo "WARNING: High disk usage: ${DISK_USAGE}%"
fi

echo "OK: All checks passed"
```

**Log Monitoring**:
```bash
# Monitor for errors
sudo journalctl -u twitch-ollama-chatbot -f | grep -i error

# Monitor performance
sudo journalctl -u twitch-ollama-chatbot | grep "response_time" | tail -10
```

### Maintenance Tasks

**Weekly Maintenance**:
```bash
#!/bin/bash
# weekly-maintenance.sh

# Update system packages
sudo apt update && sudo apt upgrade -y

# Clean old logs
sudo journalctl --vacuum-time=30d

# Restart service for memory cleanup
sudo systemctl restart twitch-ollama-chatbot

# Run backup
/usr/local/bin/chatbot-backup

# Check service health
systemctl status twitch-ollama-chatbot
```

**Monthly Maintenance**:
```bash
#!/bin/bash
# monthly-maintenance.sh

# Update Docker images
docker-compose pull
docker-compose up -d

# Clean Docker system
docker system prune -f

# Analyze database performance
mysql -u chatbot -p twitch_bot -e "ANALYZE TABLE messages, channel_config, user_response_cooldowns;"

# Review and rotate logs
logrotate -f /etc/logrotate.d/twitch-ollama-chatbot
```

### Performance Monitoring

**Key Metrics to Monitor**:
- Service uptime and restarts
- Memory and CPU usage
- Database query performance
- Ollama response times
- Message generation success rate
- Error rates and types

**Monitoring Tools**:
- **System**: htop, iotop, netstat
- **Logs**: journalctl, tail, grep
- **Database**: MySQL Workbench, phpMyAdmin
- **Docker**: docker stats, docker logs

For production deployments, consider implementing proper monitoring solutions like Prometheus, Grafana, or cloud-native monitoring services.