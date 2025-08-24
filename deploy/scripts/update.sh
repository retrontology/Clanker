#!/bin/bash
# Twitch Ollama Chatbot - Update Script

set -e

# Configuration
INSTALL_DIR="/opt/twitch-ollama-chatbot"
BACKUP_DIR="/var/backups/twitch-ollama-chatbot"
SERVICE_NAME="twitch-ollama-chatbot"

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check if running as root
check_root() {
    if [[ $EUID -ne 0 ]]; then
        log_error "This script must be run as root (use sudo)"
        exit 1
    fi
}

# Create backup before update
create_backup() {
    log_info "Creating backup before update..."
    
    if [[ -f "$INSTALL_DIR/../deploy/scripts/backup.sh" ]]; then
        bash "$INSTALL_DIR/../deploy/scripts/backup.sh"
        log_success "Backup created successfully"
    else
        log_warning "Backup script not found, proceeding without backup"
    fi
}

# Stop service
stop_service() {
    log_info "Stopping $SERVICE_NAME service..."
    
    if systemctl is-active --quiet "$SERVICE_NAME"; then
        systemctl stop "$SERVICE_NAME"
        log_success "Service stopped"
    else
        log_info "Service was not running"
    fi
}

# Update application files
update_application() {
    log_info "Updating application files..."
    
    # Backup current installation
    if [[ -d "$INSTALL_DIR.backup" ]]; then
        rm -rf "$INSTALL_DIR.backup"
    fi
    cp -r "$INSTALL_DIR" "$INSTALL_DIR.backup"
    
    # Update application code (assuming files are in current directory)
    cp -r chatbot/ "$INSTALL_DIR/"
    cp requirements.txt "$INSTALL_DIR/"
    cp setup.py "$INSTALL_DIR/"
    cp blocked_words.txt "$INSTALL_DIR/"
    
    # Preserve ownership
    chown -R chatbot:chatbot "$INSTALL_DIR/chatbot" "$INSTALL_DIR/requirements.txt" \
                             "$INSTALL_DIR/setup.py" "$INSTALL_DIR/blocked_words.txt"
    
    log_success "Application files updated"
}

# Update dependencies
update_dependencies() {
    log_info "Updating Python dependencies..."
    
    # Activate virtual environment and update dependencies
    sudo -u chatbot "$INSTALL_DIR/venv/bin/pip" install --upgrade pip
    sudo -u chatbot "$INSTALL_DIR/venv/bin/pip" install -r "$INSTALL_DIR/requirements.txt" --upgrade
    
    # Reinstall application
    sudo -u chatbot "$INSTALL_DIR/venv/bin/pip" install -e "$INSTALL_DIR"
    
    log_success "Dependencies updated"
}

# Update systemd service if needed
update_service() {
    log_info "Checking for service file updates..."
    
    if [[ -f "deploy/systemd/twitch-ollama-chatbot.service" ]]; then
        # Compare service files
        if ! cmp -s "deploy/systemd/twitch-ollama-chatbot.service" "/etc/systemd/system/twitch-ollama-chatbot.service"; then
            log_info "Updating systemd service file..."
            cp "deploy/systemd/twitch-ollama-chatbot.service" "/etc/systemd/system/"
            systemctl daemon-reload
            log_success "Service file updated"
        else
            log_info "Service file is up to date"
        fi
    fi
}

# Run database migrations if needed
run_migrations() {
    log_info "Checking for database migrations..."
    
    # Run any database migrations
    sudo -u chatbot "$INSTALL_DIR/venv/bin/python" -c "
import sys
sys.path.insert(0, '$INSTALL_DIR')
from chatbot.database.migrations import run_migrations
run_migrations()
" 2>/dev/null || log_info "No migrations to run"
    
    log_success "Database migrations completed"
}

# Start service
start_service() {
    log_info "Starting $SERVICE_NAME service..."
    
    systemctl start "$SERVICE_NAME"
    
    # Wait a moment and check if service started successfully
    sleep 5
    if systemctl is-active --quiet "$SERVICE_NAME"; then
        log_success "Service started successfully"
    else
        log_error "Service failed to start"
        log_info "Check service status: systemctl status $SERVICE_NAME"
        log_info "Check logs: journalctl -u $SERVICE_NAME -f"
        exit 1
    fi
}

# Verify update
verify_update() {
    log_info "Verifying update..."
    
    # Check service status
    if systemctl is-active --quiet "$SERVICE_NAME"; then
        log_success "Service is running"
    else
        log_error "Service is not running"
        return 1
    fi
    
    # Check logs for any immediate errors
    if journalctl -u "$SERVICE_NAME" --since "1 minute ago" | grep -i error > /dev/null; then
        log_warning "Errors found in recent logs"
        log_info "Check logs: journalctl -u $SERVICE_NAME -f"
    else
        log_success "No errors in recent logs"
    fi
    
    log_success "Update verification completed"
}

# Rollback function
rollback() {
    log_error "Rolling back to previous version..."
    
    # Stop service
    systemctl stop "$SERVICE_NAME" || true
    
    # Restore backup
    if [[ -d "$INSTALL_DIR.backup" ]]; then
        rm -rf "$INSTALL_DIR"
        mv "$INSTALL_DIR.backup" "$INSTALL_DIR"
        log_info "Files restored from backup"
        
        # Start service
        systemctl start "$SERVICE_NAME"
        log_info "Service restarted with previous version"
    else
        log_error "No backup found for rollback"
    fi
}

# Main update function
main() {
    log_info "Starting update process for Twitch Ollama Chatbot..."
    
    check_root
    
    # Set trap for rollback on error
    trap 'rollback; exit 1' ERR
    
    create_backup
    stop_service
    update_application
    update_dependencies
    update_service
    run_migrations
    start_service
    verify_update
    
    # Clean up backup on success
    if [[ -d "$INSTALL_DIR.backup" ]]; then
        rm -rf "$INSTALL_DIR.backup"
        log_info "Temporary backup cleaned up"
    fi
    
    log_success "Update completed successfully!"
    log_info "Service status: systemctl status $SERVICE_NAME"
    log_info "View logs: journalctl -u $SERVICE_NAME -f"
}

# Handle script arguments
case "${1:-}" in
    --rollback)
        log_info "Manual rollback requested"
        rollback
        exit 0
        ;;
    --help|-h)
        echo "Usage: $0 [--rollback] [--help]"
        echo "  --rollback  Rollback to previous version"
        echo "  --help      Show this help message"
        exit 0
        ;;
    *)
        main "$@"
        ;;
esac