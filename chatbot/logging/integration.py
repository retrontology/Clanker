"""
Integration utilities for logging and metrics throughout the chatbot application.

This module provides helper functions and decorators to easily integrate
structured logging and metrics collection into existing components.
"""

import asyncio
import time
from functools import wraps
from typing import Any, Callable, Dict, Optional

from .logger import get_logger
from .metrics import MetricsManager


class LoggingMixin:
    """
    Mixin class to add logging capabilities to any class.
    
    Usage:
        class MyComponent(LoggingMixin):
            def __init__(self):
                super().__init__()
                self.setup_logging("my_component")
    """
    
    def setup_logging(self, component_name: str, **logger_kwargs):
        """Set up logging for the component."""
        self.logger = get_logger(component_name, **logger_kwargs)
        self.component_name = component_name
    
    def log_operation(self, operation: str, **context):
        """Log an operation with component context."""
        self.logger.info(f"{self.component_name}: {operation}", **context)
    
    def log_error(self, operation: str, error: Exception, **context):
        """Log an error with component context."""
        self.logger.error(
            f"{self.component_name}: {operation} failed",
            error=str(error),
            error_type=type(error).__name__,
            **context
        )
    
    def log_warning(self, operation: str, reason: str, **context):
        """Log a warning with component context."""
        self.logger.warning(
            f"{self.component_name}: {operation} warning",
            reason=reason,
            **context
        )


def log_async_operation(operation_name: str, include_timing: bool = True):
    """
    Decorator to log async operations with optional timing.
    
    Args:
        operation_name: Name of the operation for logging
        include_timing: Whether to include execution time in logs
    
    Usage:
        @log_async_operation("generate_message")
        async def generate_message(self, channel: str):
            # Implementation here
            pass
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(self, *args, **kwargs):
            # Get logger from self if available, otherwise create one
            logger = getattr(self, 'logger', None) or get_logger(func.__module__)
            
            start_time = time.time() if include_timing else None
            
            try:
                # Extract context from common parameters
                context = {}
                if args and isinstance(args[0], str):
                    context['channel'] = args[0]
                
                logger.debug(f"Starting {operation_name}", **context)
                
                result = await func(self, *args, **kwargs)
                
                if include_timing and start_time:
                    duration = (time.time() - start_time) * 1000  # Convert to ms
                    context['duration_ms'] = round(duration, 2)
                
                logger.info(f"Completed {operation_name}", **context)
                return result
                
            except Exception as e:
                context = {}
                if args and isinstance(args[0], str):
                    context['channel'] = args[0]
                
                if include_timing and start_time:
                    duration = (time.time() - start_time) * 1000
                    context['duration_ms'] = round(duration, 2)
                
                logger.error(
                    f"Failed {operation_name}",
                    error=str(e),
                    error_type=type(e).__name__,
                    **context
                )
                raise
        
        return wrapper
    return decorator


def track_metrics(metrics_manager: MetricsManager, operation_type: str = "generation"):
    """
    Decorator to automatically track metrics for operations.
    
    Args:
        metrics_manager: MetricsManager instance
        operation_type: Type of operation for metrics categorization
    
    Usage:
        @track_metrics(self.metrics, "ollama_request")
        async def call_ollama(self, channel: str, prompt: str):
            # Implementation here
            pass
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(self, *args, **kwargs):
            start_time = time.time()
            channel = args[0] if args and isinstance(args[0], str) else "unknown"
            
            try:
                result = await func(self, *args, **kwargs)
                
                # Record success and timing
                duration_ms = (time.time() - start_time) * 1000
                await metrics_manager.record_response_time(channel, duration_ms)
                await metrics_manager.record_success(channel, operation_type)
                
                return result
                
            except asyncio.TimeoutError:
                duration_ms = (time.time() - start_time) * 1000
                await metrics_manager.record_response_time(channel, duration_ms)
                await metrics_manager.record_error(channel, "timeout", operation_type)
                raise
                
            except Exception as e:
                duration_ms = (time.time() - start_time) * 1000
                await metrics_manager.record_response_time(channel, duration_ms)
                
                # Categorize error types
                error_type = "unknown"
                if "connection" in str(e).lower():
                    error_type = "connection"
                elif "timeout" in str(e).lower():
                    error_type = "timeout"
                elif "api" in str(e).lower():
                    error_type = "api_error"
                
                await metrics_manager.record_error(channel, error_type, operation_type)
                raise
        
        return wrapper
    return decorator


class PerformanceMonitor:
    """
    Context manager for monitoring performance of code blocks.
    
    Usage:
        async with PerformanceMonitor(metrics_manager, "database_query", channel="test"):
            result = await db.get_messages(channel)
    """
    
    def __init__(
        self,
        metrics_manager: MetricsManager,
        operation_name: str,
        channel: str,
        operation_type: str = "operation"
    ):
        self.metrics_manager = metrics_manager
        self.operation_name = operation_name
        self.channel = channel
        self.operation_type = operation_type
        self.logger = get_logger("performance_monitor")
        self.start_time = None
    
    async def __aenter__(self):
        self.start_time = time.time()
        self.logger.debug(f"Starting {self.operation_name}", channel=self.channel)
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        duration_ms = (time.time() - self.start_time) * 1000
        
        if exc_type is None:
            # Success
            await self.metrics_manager.record_response_time(self.channel, duration_ms)
            await self.metrics_manager.record_success(self.channel, self.operation_type)
            self.logger.debug(
                f"Completed {self.operation_name}",
                channel=self.channel,
                duration_ms=round(duration_ms, 2)
            )
        else:
            # Error occurred
            await self.metrics_manager.record_response_time(self.channel, duration_ms)
            
            error_type = "unknown"
            if exc_type == asyncio.TimeoutError:
                error_type = "timeout"
            elif "connection" in str(exc_val).lower():
                error_type = "connection"
            
            await self.metrics_manager.record_error(self.channel, error_type, self.operation_type)
            self.logger.error(
                f"Failed {self.operation_name}",
                channel=self.channel,
                duration_ms=round(duration_ms, 2),
                error=str(exc_val),
                error_type=exc_type.__name__
            )


def setup_component_logging(component_name: str):
    """
    Class decorator to automatically set up logging for a component.
    
    Args:
        component_name: Name for the logger
    
    Usage:
        @setup_component_logging("ollama_client")
        class OllamaClient:
            def __init__(self):
                # self.logger is now available
                pass
    """
    def decorator(cls):
        original_init = cls.__init__
        
        def new_init(self, *args, **kwargs):
            original_init(self, *args, **kwargs)
            self.logger = get_logger(component_name)
            self.component_name = component_name
        
        cls.__init__ = new_init
        return cls
    
    return decorator


# Utility functions for common logging patterns

async def log_message_processing(
    logger,
    channel: str,
    user: str,
    message_content: str,
    processing_result: str,
    **extra_context
):
    """Log message processing events."""
    logger.info(
        "Message processed",
        channel=channel,
        user=user,
        message_length=len(message_content),
        result=processing_result,
        **extra_context
    )


async def log_generation_event(
    logger,
    metrics_manager: MetricsManager,
    channel: str,
    generation_type: str,
    success: bool,
    duration_ms: float,
    model_used: str,
    **extra_context
):
    """Log message generation events with metrics."""
    if success:
        logger.info(
            "Message generated successfully",
            channel=channel,
            generation_type=generation_type,
            duration_ms=duration_ms,
            model=model_used,
            **extra_context
        )
        await metrics_manager.record_success(channel, generation_type)
    else:
        logger.warning(
            "Message generation failed",
            channel=channel,
            generation_type=generation_type,
            duration_ms=duration_ms,
            model=model_used,
            **extra_context
        )
        await metrics_manager.record_error(channel, "generation_failed", generation_type)
    
    await metrics_manager.record_response_time(channel, duration_ms)


async def log_filter_event(
    logger,
    metrics_manager: MetricsManager,
    channel: str,
    filter_type: str,
    blocked: bool,
    content_sample: str = None,
    **extra_context
):
    """Log content filtering events."""
    if blocked:
        logger.warning(
            "Content blocked by filter",
            channel=channel,
            filter_type=filter_type,
            content_sample=content_sample[:50] + "..." if content_sample and len(content_sample) > 50 else content_sample,
            **extra_context
        )
        await metrics_manager.record_filter_block(channel, filter_type)
    else:
        logger.debug(
            "Content passed filter",
            channel=channel,
            filter_type=filter_type,
            **extra_context
        )


async def log_rate_limit_event(
    logger,
    metrics_manager: MetricsManager,
    channel: str,
    limit_type: str,
    remaining_seconds: float,
    **extra_context
):
    """Log rate limiting events."""
    logger.debug(
        "Rate limit applied",
        channel=channel,
        limit_type=limit_type,
        remaining_seconds=remaining_seconds,
        **extra_context
    )
    await metrics_manager.record_rate_limit_hit(channel, limit_type)