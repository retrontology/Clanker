#!/bin/bash
# Twitch Ollama Chatbot - Installation Script for Linux

set -e

# Configuration
INSTALL_DIR="/opt/twitch-ollama-chatbot"
SERVICE_USER="chatbot"
SERVICE_GROUP="chatbot"
PYTHON_VERSION="3.11"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Logging functions
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

# Check system requirements
check_requirements() {
    log_info "Checking system requirements..."
    
    # Check Python version
    if ! command -v python3 &> /dev/null; then
        log_error "Python 3 is not installed"
        exit 1
    fi
    
    PYTHON_VER=$(python3 -c 'import sys; print(".".join(map(str, sys.version_info[:2])))')
    if [[ $(echo "$PYTHON_VER >= $PYTHON_VERSION" | bc -l) -eq 0 ]]; then
        log_error "Python $PYTHON_VERSION or higher is required (found $PYTHON_VER)"
        exit 1
    fi
    
    # Check pip
    if ! command -v pip3 &> /dev/null; then
        log_error "pip3 is not installed"
        exit 1
    fi
    
    # Check systemctl
    if ! command -v systemctl &> /dev/null; then
        log_error "systemd is not available"
        exit 1
    fi
    
    log_success "System requirements check passed"
}

# Create service user
create_user() {
    log_info "Creating service user and group..."
    
    if ! getent group "$SERVICE_GROUP" > /dev/null 2>&1; then
        groupadd --system "$SERVICE_GROUP"
        log_success "Created group: $SERVICE_GROUP"
    else
        log_info "Group $SERVICE_GROUP already exists"
    fi
    
    if ! getent passwd "$SERVICE_USER" > /dev/null 2>&1; then
        useradd --system --gid "$SERVICE_GROUP" --home-dir "$INSTALL_DIR" \
                --shell /bin/false --comment "Twitch Ollama Chatbot" "$SERVICE_USER"
        log_success "Created user: $SERVICE_USER"
    else
        log_info "User $SERVICE_USER already exists"
    fi
}

# Install application
install_application() {
    log_info "Installing application to $INSTALL_DIR..."
    
    # Create installation directory
    mkdir -p "$INSTALL_DIR"
    mkdir -p "$INSTALL_DIR/data"
    mkdir -p "$INSTALL_DIR/logs"
    
    # Copy application files
    cp -r chatbot/ "$INSTALL_DIR/"
    cp requirements.txt "$INSTALL_DIR/"
    cp setup.py "$INSTALL_DIR/"
    cp blocked_words.txt "$INSTALL_DIR/"
    
    # Copy environment template
    if [[ ! -f "$INSTALL_DIR/.env" ]]; then
        cp .env.example "$INSTALL_DIR/.env"
        log_info "Created .env file from template - please configure it"
    else
        log_info ".env file already exists - skipping"
    fi
    
    # Set ownership
    chown -R "$SERVICE_USER:$SERVICE_GROUP" "$INSTALL_DIR"
    
    # Set permissions
    chmod 755 "$INSTALL_DIR"
    chmod 750 "$INSTALL_DIR/data" "$INSTALL_DIR/logs"
    chmod 640 "$INSTALL_DIR/.env"
    
    log_success "Application files installed"
}

# Create Python virtual environment
create_venv() {
    log_info "Creating Python virtual environment..."
    
    sudo -u "$SERVICE_USER" python3 -m venv "$INSTALL_DIR/venv"
    
    # Upgrade pip
    sudo -u "$SERVICE_USER" "$INSTALL_DIR/venv/bin/pip" install --upgrade pip
    
    # Install dependencies
    sudo -u "$SERVICE_USER" "$INSTALL_DIR/venv/bin/pip" install -r "$INSTALL_DIR/requirements.txt"
    
    # Install application in development mode
    sudo -u "$SERVICE_USER" "$INSTALL_DIR/venv/bin/pip" install -e "$INSTALL_DIR"
    
    log_success "Virtual environment created and dependencies installed"
}

# Install systemd service
install_service() {
    log_info "Installing systemd service..."
    
    # Copy service file
    cp deploy/systemd/twitch-ollama-chatbot.service /etc/systemd/system/
    
    # Reload systemd
    systemctl daemon-reload
    
    # Enable service (but don't start it yet)
    systemctl enable twitch-ollama-chatbot.service
    
    log_success "Systemd service installed and enabled"
}

# Create log rotation configuration
setup_logrotate() {
    log_info "Setting up log rotation..."
    
    cat > /etc/logrotate.d/twitch-ollama-chatbot << EOF
$INSTALL_DIR/logs/*.log {
    daily
    missingok
    rotate 30
    compress
    delaycompress
    notifempty
    create 640 $SERVICE_USER $SERVICE_GROUP
    postrotate
        systemctl reload twitch-ollama-chatbot.service > /dev/null 2>&1 || true
    endscript
}
EOF
    
    log_success "Log rotation configured"
}

# Main installation function
main() {
    log_info "Starting Twitch Ollama Chatbot installation..."
    
    check_root
    check_requirements
    create_user
    install_application
    create_venv
    install_service
    setup_logrotate
    
    log_success "Installation completed successfully!"
    echo
    log_info "Next steps:"
    echo "1. Configure your settings in $INSTALL_DIR/.env"
    echo "2. Set up your Twitch OAuth credentials"
    echo "3. Configure your Ollama server URL and model"
    echo "4. Start the service: sudo systemctl start twitch-ollama-chatbot"
    echo "5. Check status: sudo systemctl status twitch-ollama-chatbot"
    echo "6. View logs: sudo journalctl -u twitch-ollama-chatbot -f"
    echo
    log_warning "Remember to configure your .env file before starting the service!"
}

# Run main function
main "$@"