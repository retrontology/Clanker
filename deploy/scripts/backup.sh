#!/bin/bash
# Twitch Ollama Chatbot - Backup Script

set -e

# Configuration
INSTALL_DIR="/opt/twitch-ollama-chatbot"
BACKUP_DIR="/var/backups/twitch-ollama-chatbot"
RETENTION_DAYS=30
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
BACKUP_NAME="chatbot_backup_${TIMESTAMP}"

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Create backup directory
create_backup_dir() {
    mkdir -p "$BACKUP_DIR"
    log_info "Created backup directory: $BACKUP_DIR"
}

# Backup database
backup_database() {
    log_info "Backing up database..."
    
    # Check if SQLite database exists
    if [[ -f "$INSTALL_DIR/data/chatbot.db" ]]; then
        cp "$INSTALL_DIR/data/chatbot.db" "$BACKUP_DIR/${BACKUP_NAME}_database.db"
        log_info "SQLite database backed up"
    fi
    
    # For MySQL backups (if configured)
    if [[ -f "$INSTALL_DIR/.env" ]]; then
        source "$INSTALL_DIR/.env"
        if [[ "$DATABASE_TYPE" == "mysql" ]]; then
            log_info "Creating MySQL backup..."
            mysqldump -h"$MYSQL_HOST" -u"$MYSQL_USER" -p"$MYSQL_PASSWORD" \
                      "$MYSQL_DATABASE" > "$BACKUP_DIR/${BACKUP_NAME}_mysql.sql"
            log_info "MySQL database backed up"
        fi
    fi
}

# Backup configuration
backup_config() {
    log_info "Backing up configuration..."
    
    # Create config backup directory
    mkdir -p "$BACKUP_DIR/${BACKUP_NAME}_config"
    
    # Backup environment file (excluding sensitive data)
    if [[ -f "$INSTALL_DIR/.env" ]]; then
        # Create sanitized config backup
        grep -v -E "(PASSWORD|SECRET|KEY)" "$INSTALL_DIR/.env" > "$BACKUP_DIR/${BACKUP_NAME}_config/env_sanitized"
        log_info "Environment configuration backed up (sanitized)"
    fi
    
    # Backup blocked words file
    if [[ -f "$INSTALL_DIR/blocked_words.txt" ]]; then
        cp "$INSTALL_DIR/blocked_words.txt" "$BACKUP_DIR/${BACKUP_NAME}_config/"
        log_info "Blocked words file backed up"
    fi
}

# Backup logs
backup_logs() {
    log_info "Backing up recent logs..."
    
    if [[ -d "$INSTALL_DIR/logs" ]]; then
        # Create logs backup directory
        mkdir -p "$BACKUP_DIR/${BACKUP_NAME}_logs"
        
        # Copy recent log files (last 7 days)
        find "$INSTALL_DIR/logs" -name "*.log*" -mtime -7 -exec cp {} "$BACKUP_DIR/${BACKUP_NAME}_logs/" \;
        log_info "Recent logs backed up"
    fi
}

# Create compressed archive
create_archive() {
    log_info "Creating compressed archive..."
    
    cd "$BACKUP_DIR"
    tar -czf "${BACKUP_NAME}.tar.gz" "${BACKUP_NAME}"_*
    
    # Remove individual backup files
    rm -rf "${BACKUP_NAME}"_*
    
    log_info "Backup archive created: ${BACKUP_NAME}.tar.gz"
}

# Clean old backups
cleanup_old_backups() {
    log_info "Cleaning up old backups (older than $RETENTION_DAYS days)..."
    
    find "$BACKUP_DIR" -name "chatbot_backup_*.tar.gz" -mtime +$RETENTION_DAYS -delete
    
    log_info "Old backups cleaned up"
}

# Verify backup
verify_backup() {
    log_info "Verifying backup..."
    
    if [[ -f "$BACKUP_DIR/${BACKUP_NAME}.tar.gz" ]]; then
        # Test archive integrity
        if tar -tzf "$BACKUP_DIR/${BACKUP_NAME}.tar.gz" > /dev/null 2>&1; then
            log_info "Backup verification successful"
            
            # Show backup size
            BACKUP_SIZE=$(du -h "$BACKUP_DIR/${BACKUP_NAME}.tar.gz" | cut -f1)
            log_info "Backup size: $BACKUP_SIZE"
        else
            log_error "Backup verification failed - archive is corrupted"
            exit 1
        fi
    else
        log_error "Backup file not found"
        exit 1
    fi
}

# Main backup function
main() {
    log_info "Starting backup process..."
    
    # Check if running as root or chatbot user
    if [[ $EUID -ne 0 ]] && [[ $(whoami) != "chatbot" ]]; then
        log_error "This script must be run as root or chatbot user"
        exit 1
    fi
    
    # Stop service temporarily for consistent backup
    if systemctl is-active --quiet twitch-ollama-chatbot; then
        log_info "Stopping chatbot service for backup..."
        systemctl stop twitch-ollama-chatbot
        SERVICE_WAS_RUNNING=true
    else
        SERVICE_WAS_RUNNING=false
    fi
    
    # Perform backup
    create_backup_dir
    backup_database
    backup_config
    backup_logs
    create_archive
    verify_backup
    cleanup_old_backups
    
    # Restart service if it was running
    if [[ "$SERVICE_WAS_RUNNING" == true ]]; then
        log_info "Restarting chatbot service..."
        systemctl start twitch-ollama-chatbot
    fi
    
    log_info "Backup completed successfully!"
    log_info "Backup location: $BACKUP_DIR/${BACKUP_NAME}.tar.gz"
}

# Handle script interruption
trap 'log_error "Backup interrupted"; exit 1' INT TERM

# Run main function
main "$@"