"""
Structured logging implementation for the Twitch Ollama Chatbot.

Provides JSON and console logging formats with configurable levels,
file rotation, and security considerations for sensitive data.
"""

import json
import logging
import logging.handlers
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional


class JsonFormatter(logging.Formatter):
    """Custom formatter for JSON log output."""
    
    def format(self, record: logging.LogRecord) -> str:
        """Format log record as JSON."""
        log_data = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        
        # Add extra fields from the record
        if hasattr(record, 'extra_data'):
            log_data.update(record.extra_data)
        
        # Add exception info if present
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)
        
        return json.dumps(log_data, ensure_ascii=False)


class ConsoleFormatter(logging.Formatter):
    """Custom formatter for console output with colors and structured data."""
    
    # ANSI color codes
    COLORS = {
        'DEBUG': '\033[36m',    # Cyan
        'INFO': '\033[32m',     # Green
        'WARNING': '\033[33m',  # Yellow
        'ERROR': '\033[31m',    # Red
        'CRITICAL': '\033[35m', # Magenta
        'RESET': '\033[0m'      # Reset
    }
    
    def format(self, record: logging.LogRecord) -> str:
        """Format log record for console output."""
        # Get color for log level
        color = self.COLORS.get(record.levelname, '')
        reset = self.COLORS['RESET']
        
        # Format timestamp
        timestamp = datetime.fromtimestamp(record.created).strftime('%Y-%m-%d %H:%M:%S')
        
        # Build base message
        message = f"{timestamp} {color}{record.levelname:<8}{reset} [{record.name}] {record.getMessage()}"
        
        # Add extra context if available
        if hasattr(record, 'extra_data') and record.extra_data:
            context_parts = []
            for key, value in record.extra_data.items():
                # Don't log sensitive data in console
                if key.lower() in ['token', 'password', 'secret', 'key']:
                    value = '[REDACTED]'
                context_parts.append(f"{key}={value}")
            
            if context_parts:
                message += f" | {', '.join(context_parts)}"
        
        # Add exception info if present
        if record.exc_info:
            message += f"\n{self.formatException(record.exc_info)}"
        
        return message


class StructuredLogger:
    """
    Structured logger with support for JSON and console output formats.
    
    Features:
    - Configurable output formats (JSON for production, console for development)
    - File rotation with size and time-based rotation
    - Security considerations (sensitive data filtering)
    - Structured logging with extra context fields
    """
    
    def __init__(
        self,
        name: str,
        level: str = "INFO",
        format_type: str = "console",
        log_file: Optional[str] = None,
        max_file_size: int = 10 * 1024 * 1024,  # 10MB
        backup_count: int = 5,
        enable_console: bool = True
    ):
        """
        Initialize structured logger.
        
        Args:
            name: Logger name
            level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
            format_type: Output format ('json' or 'console')
            log_file: Path to log file (optional)
            max_file_size: Maximum file size before rotation (bytes)
            backup_count: Number of backup files to keep
            enable_console: Whether to enable console output
        """
        self.logger = logging.getLogger(name)
        self.logger.setLevel(getattr(logging, level.upper()))
        self.format_type = format_type
        
        # Clear any existing handlers
        self.logger.handlers.clear()
        
        # Add console handler if enabled
        if enable_console:
            console_handler = logging.StreamHandler()
            if format_type == "json":
                console_handler.setFormatter(JsonFormatter())
            else:
                console_handler.setFormatter(ConsoleFormatter())
            self.logger.addHandler(console_handler)
        
        # Add file handler if log file specified
        if log_file:
            self._setup_file_handler(log_file, max_file_size, backup_count)
    
    def _setup_file_handler(self, log_file: str, max_file_size: int, backup_count: int):
        """Set up rotating file handler."""
        # Ensure log directory exists
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Create rotating file handler
        file_handler = logging.handlers.RotatingFileHandler(
            filename=log_file,
            maxBytes=max_file_size,
            backupCount=backup_count,
            encoding='utf-8'
        )
        
        # Always use JSON format for file output
        file_handler.setFormatter(JsonFormatter())
        self.logger.addHandler(file_handler)
    
    def _log(self, level: str, message: str, **context):
        """Internal logging method with context."""
        # Filter sensitive data from context
        filtered_context = self._filter_sensitive_data(context)
        
        # Create log record with extra data
        extra = {'extra_data': filtered_context} if filtered_context else {}
        self.logger.log(getattr(logging, level), message, extra=extra)
    
    def _filter_sensitive_data(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """Filter sensitive data from log context."""
        sensitive_keys = {
            'token', 'password', 'secret', 'key', 'auth', 'credential',
            'access_token', 'refresh_token', 'oauth_token', 'api_key'
        }
        
        filtered = {}
        for key, value in context.items():
            key_lower = key.lower()
            if any(sensitive in key_lower for sensitive in sensitive_keys):
                # For tokens, show only first/last few characters
                if isinstance(value, str) and len(value) > 8:
                    filtered[key] = f"{value[:4]}...{value[-4:]}"
                else:
                    filtered[key] = "[REDACTED]"
            else:
                filtered[key] = value
        
        return filtered
    
    def debug(self, message: str, **context):
        """Log debug message with context."""
        self._log("DEBUG", message, **context)
    
    def info(self, message: str, **context):
        """Log info message with context."""
        self._log("INFO", message, **context)
    
    def warning(self, message: str, **context):
        """Log warning message with context."""
        self._log("WARNING", message, **context)
    
    def error(self, message: str, **context):
        """Log error message with context."""
        self._log("ERROR", message, **context)
    
    def critical(self, message: str, **context):
        """Log critical message with context."""
        self._log("CRITICAL", message, **context)
    
    def exception(self, message: str, **context):
        """Log exception with traceback."""
        # Filter sensitive data from context
        filtered_context = self._filter_sensitive_data(context)
        extra = {'extra_data': filtered_context} if filtered_context else {}
        self.logger.exception(message, extra=extra)


# Global logger instances
_loggers: Dict[str, StructuredLogger] = {}


def get_logger(
    name: str,
    level: Optional[str] = None,
    format_type: Optional[str] = None,
    log_file: Optional[str] = None
) -> StructuredLogger:
    """
    Get or create a structured logger instance.
    
    Args:
        name: Logger name
        level: Log level (uses environment variable LOG_LEVEL if not specified)
        format_type: Format type (uses environment variable LOG_FORMAT if not specified)
        log_file: Log file path (uses environment variable LOG_FILE if not specified)
    
    Returns:
        StructuredLogger instance
    """
    # Use environment variables as defaults
    if level is None:
        level = os.getenv('LOG_LEVEL', 'INFO')
    if format_type is None:
        format_type = os.getenv('LOG_FORMAT', 'console')
    if log_file is None:
        log_file = os.getenv('LOG_FILE')
    
    # Create cache key
    cache_key = f"{name}:{level}:{format_type}:{log_file}"
    
    # Return existing logger if available
    if cache_key in _loggers:
        return _loggers[cache_key]
    
    # Create new logger
    logger = StructuredLogger(
        name=name,
        level=level,
        format_type=format_type,
        log_file=log_file
    )
    
    _loggers[cache_key] = logger
    return logger