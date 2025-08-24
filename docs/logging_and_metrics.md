# Logging and Metrics System

This document describes the comprehensive logging and metrics system implemented for the Twitch Ollama Chatbot.

## Overview

The logging and metrics system provides:

- **Structured Logging**: JSON and console output formats with configurable levels
- **Performance Metrics**: Response time tracking, success rates, and error monitoring
- **File Rotation**: Automatic log file rotation with size and time-based policies
- **Security**: Automatic filtering of sensitive data from logs
- **Integration Utilities**: Decorators and mixins for easy integration

## Components

### StructuredLogger

The core logging component that supports both JSON and console output formats.

```python
from chatbot.logging import StructuredLogger

# Console format (development)
logger = StructuredLogger(
    name="my_component",
    level="INFO",
    format_type="console"
)

# JSON format (production)
logger = StructuredLogger(
    name="my_component", 
    level="INFO",
    format_type="json",
    log_file="logs/chatbot.log"
)

# Usage
logger.info("Message processed", channel="testchannel", user="user123")
logger.warning("Rate limit hit", remaining_seconds=30)
logger.error("Database connection failed", error="Connection timeout")
```

### MetricsManager

Collects and stores performance metrics in the database.

```python
from chatbot.logging import MetricsManager

metrics = MetricsManager(db_manager)

# Record metrics
await metrics.record_response_time("channel1", 1500.0)  # milliseconds
await metrics.record_success("channel1", "generation")
await metrics.record_error("channel1", "timeout", "ollama_request")
await metrics.record_filter_block("channel1", "input")
await metrics.record_rate_limit_hit("channel1", "spontaneous")

# Get performance statistics
stats = await metrics.get_performance_stats("channel1", hours=24)
print(stats)
```

## Integration Patterns

### 1. LoggingMixin

Add logging capabilities to any class:

```python
from chatbot.logging import LoggingMixin

class MyComponent(LoggingMixin):
    def __init__(self):
        super().__init__()
        self.setup_logging("my_component")
    
    async def do_something(self):
        self.log_operation("Starting operation", param1="value1")
        try:
            # Do work
            pass
        except Exception as e:
            self.log_error("Operation failed", e, param1="value1")
```

### 2. Decorators

Automatic logging and metrics for methods:

```python
from chatbot.logging import log_async_operation, track_metrics

class OllamaClient:
    @log_async_operation("ollama_request", include_timing=True)
    async def generate_message(self, channel: str, prompt: str):
        # Implementation automatically logged with timing
        pass
```

### 3. Context Manager

Monitor performance of code blocks:

```python
from chatbot.logging import PerformanceMonitor

async with PerformanceMonitor(metrics_manager, "database_query", channel, "db_operation"):
    result = await db.get_messages(channel)
```

### 4. Class Decorator

Automatic logging setup for entire classes:

```python
from chatbot.logging import setup_component_logging

@setup_component_logging("content_filter")
class ContentFilter:
    def __init__(self):
        # self.logger is automatically available
        pass
```

## Configuration

### Environment Variables

```bash
# Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
LOG_LEVEL=INFO

# Output format (console, json)
LOG_FORMAT=console

# Log file path (optional)
LOG_FILE=logs/chatbot.log

# File rotation settings
LOG_MAX_SIZE=10485760  # 10MB
LOG_BACKUP_COUNT=5
```

### Programmatic Configuration

```python
from chatbot.logging import get_logger

# Get logger with environment defaults
logger = get_logger("component_name")

# Override specific settings
logger = get_logger(
    "component_name",
    level="DEBUG",
    format_type="json",
    log_file="custom.log"
)
```

## Log Formats

### Console Format (Development)

```
2024-01-15 10:30:45 INFO     [ollama_client] Message generated | channel=testchannel, duration_ms=1250, model=llama3.1
2024-01-15 10:30:46 WARNING  [content_filter] Content blocked | channel=testchannel, filter_type=input, reason=profanity
2024-01-15 10:30:47 ERROR    [database] Connection failed | error=timeout, retry_count=2
```

### JSON Format (Production)

```json
{
  "timestamp": "2024-01-15T10:30:45.123Z",
  "level": "INFO",
  "logger": "ollama_client",
  "message": "Message generated",
  "channel": "testchannel",
  "duration_ms": 1250,
  "model": "llama3.1"
}
```

## Security Features

### Sensitive Data Filtering

The logging system automatically filters sensitive data:

```python
logger.info("Authentication successful", 
           access_token="abc123def456ghi789",  # Becomes "abc1...i789"
           password="secret123",              # Becomes "[REDACTED]"
           user_id="12345")                   # Remains visible
```

Filtered fields include:
- `token`, `password`, `secret`, `key`
- `access_token`, `refresh_token`, `oauth_token`
- `auth`, `credential`, `api_key`

## Metrics Collection

### Automatic Metrics

The system automatically collects:

- **Response Times**: Ollama API calls, database queries, message processing
- **Success Rates**: Message generation, content filtering, database operations
- **Error Counts**: By type (timeout, connection, api_error, etc.)
- **Rate Limiting**: Spontaneous and response cooldown hits
- **Content Filtering**: Input and output filter blocks

### Custom Metrics

Add custom metrics for specific operations:

```python
# Custom operation timing
start_time = time.time()
# ... do work ...
duration_ms = (time.time() - start_time) * 1000
await metrics.record_response_time(channel, duration_ms)

# Custom success/error tracking
await metrics.record_success(channel, "custom_operation")
await metrics.record_error(channel, "custom_error", "custom_operation")
```

### Performance Statistics

Get comprehensive performance data:

```python
stats = await metrics.get_performance_stats("channel1", hours=24)

# Example output:
{
  "channel": "channel1",
  "period_hours": 24,
  "metrics": {
    "response_time": {"average": 1250.5, "count": 45, "total": 56272.5},
    "generation_success": {"average": 1.0, "count": 42, "total": 42.0},
    "generation_error_timeout": {"average": 1.0, "count": 3, "total": 3.0}
  },
  "derived": {
    "success_rate": 93.33,
    "avg_response_time_ms": 1250.5,
    "messages_per_hour": 45.0
  }
}
```

## File Rotation

Automatic log file rotation prevents disk space issues:

```python
logger = StructuredLogger(
    name="chatbot",
    log_file="logs/chatbot.log",
    max_file_size=10 * 1024 * 1024,  # 10MB
    backup_count=5                    # Keep 5 backup files
)
```

Files are rotated as:
- `chatbot.log` (current)
- `chatbot.log.1` (previous)
- `chatbot.log.2` (older)
- etc.

## Integration Examples

### IRC Handler Integration

```python
from chatbot.logging import get_logger, log_message_processing

class TwitchIRCClient:
    def __init__(self, metrics_manager):
        self.logger = get_logger("irc_client")
        self.metrics = metrics_manager
    
    async def event_message(self, message):
        await log_message_processing(
            self.logger,
            channel=message.channel.name,
            user=message.author.name,
            message_content=message.content,
            processing_result="stored"
        )
```

### Ollama Client Integration

```python
from chatbot.logging import get_logger, log_generation_event

class OllamaClient:
    def __init__(self, metrics_manager):
        self.logger = get_logger("ollama_client")
        self.metrics = metrics_manager
    
    async def generate_message(self, channel, context):
        start_time = time.time()
        try:
            response = await self._call_ollama_api(context)
            duration_ms = (time.time() - start_time) * 1000
            
            await log_generation_event(
                self.logger,
                self.metrics,
                channel=channel,
                generation_type="spontaneous",
                success=True,
                duration_ms=duration_ms,
                model_used="llama3.1"
            )
            return response
        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            await log_generation_event(
                self.logger,
                self.metrics,
                channel=channel,
                generation_type="spontaneous", 
                success=False,
                duration_ms=duration_ms,
                model_used="llama3.1",
                error=str(e)
            )
            raise
```

## Best Practices

### 1. Use Appropriate Log Levels

- **DEBUG**: Detailed information for debugging
- **INFO**: General operational information
- **WARNING**: Something unexpected but not critical
- **ERROR**: Error conditions that need attention
- **CRITICAL**: Serious errors that may cause shutdown

### 2. Include Relevant Context

Always include relevant context in log messages:

```python
# Good
logger.info("Message generated", channel="test", user="user123", duration_ms=1250)

# Bad
logger.info("Message generated")
```

### 3. Use Structured Data

Prefer structured data over string formatting:

```python
# Good
logger.error("Database query failed", query="SELECT * FROM messages", error=str(e))

# Bad
logger.error(f"Database query failed: {query} - {e}")
```

### 4. Monitor Performance

Regularly check performance statistics:

```python
# Daily performance check
stats = await metrics.get_performance_stats(channel, hours=24)
if stats["derived"]["success_rate"] < 95.0:
    logger.warning("Low success rate detected", success_rate=stats["derived"]["success_rate"])
```

### 5. Clean Up Old Data

Implement regular cleanup of old metrics:

```python
# Weekly cleanup
await metrics.cleanup_old_metrics(retention_days=7)
```

## Troubleshooting

### High Memory Usage

If memory usage is high:

1. Check metrics buffer size: `await metrics.get_session_stats()`
2. Reduce flush interval in MetricsManager
3. Implement more aggressive cleanup policies

### Log File Growth

If log files grow too quickly:

1. Reduce log level (INFO instead of DEBUG)
2. Decrease max file size for rotation
3. Reduce backup count

### Performance Impact

If logging impacts performance:

1. Use JSON format only for production
2. Disable console output in production
3. Increase metrics flush interval
4. Use async logging where possible

## Monitoring and Alerting

### Key Metrics to Monitor

- **Success Rate**: Should be > 95%
- **Average Response Time**: Should be < 2000ms
- **Error Rate**: Should be < 5%
- **Filter Block Rate**: Monitor for content issues

### Example Monitoring Script

```python
async def check_system_health():
    stats = await metrics.get_performance_stats(hours=1)
    
    if stats["derived"]["success_rate"] < 95:
        logger.critical("Low success rate", rate=stats["derived"]["success_rate"])
    
    if stats["derived"]["avg_response_time_ms"] > 2000:
        logger.warning("High response time", time=stats["derived"]["avg_response_time_ms"])
```

This comprehensive logging and metrics system provides full observability into the chatbot's operation, enabling effective monitoring, debugging, and performance optimization.