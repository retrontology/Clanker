"""
Database connection resilience and recovery systems.

This module implements exponential backoff reconnection logic,
graceful handling of partial database failures, and connection
health monitoring with automatic recovery procedures.
"""

import asyncio
import logging
import time
from typing import Optional, Dict, Any, Callable, Awaitable
from datetime import datetime, timedelta
from enum import Enum
from contextlib import asynccontextmanager

logger = logging.getLogger(__name__)


class ConnectionState(Enum):
    """Database connection states."""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    FAILED = "failed"
    RECOVERING = "recovering"


class DatabaseFailureMode(Enum):
    """Types of database failure modes."""
    READ_ONLY = "read_only"
    WRITE_ONLY = "write_only"
    FULL_FAILURE = "full_failure"


class ConnectionHealthMonitor:
    """Monitors database connection health and manages recovery."""
    
    def __init__(self, max_retries: int = 5, base_delay: float = 1.0, max_delay: float = 60.0):
        """
        Initialize connection health monitor.
        
        Args:
            max_retries: Maximum number of retry attempts
            base_delay: Base delay for exponential backoff (seconds)
            max_delay: Maximum delay between retries (seconds)
        """
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.max_delay = max_delay
        
        self.state = ConnectionState.HEALTHY
        self.failure_mode: Optional[DatabaseFailureMode] = None
        self.retry_count = 0
        self.last_failure_time: Optional[datetime] = None
        self.consecutive_failures = 0
        self.last_success_time = datetime.now()
        
        # Health check metrics
        self.health_check_interval = 30.0  # seconds
        self.health_check_timeout = 5.0    # seconds
        self.failure_threshold = 3         # consecutive failures before marking as failed
        
        # Recovery tracking
        self.recovery_start_time: Optional[datetime] = None
        self.recovery_attempts = 0
    
    def calculate_backoff_delay(self) -> float:
        """
        Calculate exponential backoff delay with jitter.
        
        Returns:
            float: Delay in seconds
        """
        if self.retry_count == 0:
            return 0
        
        # Exponential backoff: base_delay * 2^(retry_count - 1)
        delay = self.base_delay * (2 ** (self.retry_count - 1))
        
        # Cap at max_delay
        delay = min(delay, self.max_delay)
        
        # Add jitter (±20%)
        import random
        jitter = delay * 0.2 * (random.random() - 0.5)
        delay += jitter
        
        return max(0, delay)
    
    def record_success(self):
        """Record a successful database operation."""
        if self.state != ConnectionState.HEALTHY:
            logger.info(f"Database connection recovered after {self.consecutive_failures} failures")
        
        self.state = ConnectionState.HEALTHY
        self.failure_mode = None
        self.retry_count = 0
        self.consecutive_failures = 0
        self.last_success_time = datetime.now()
        self.recovery_start_time = None
        self.recovery_attempts = 0
    
    def record_failure(self, error: Exception, operation_type: str = "unknown"):
        """
        Record a database operation failure.
        
        Args:
            error: The exception that occurred
            operation_type: Type of operation that failed (read/write/connection)
        """
        self.last_failure_time = datetime.now()
        self.consecutive_failures += 1
        self.retry_count += 1
        
        # Determine failure mode based on error type
        self.failure_mode = self._classify_failure(error, operation_type)
        
        # Update connection state
        if self.consecutive_failures >= self.failure_threshold:
            if self.state == ConnectionState.HEALTHY:
                logger.warning(f"Database connection marked as failed after {self.consecutive_failures} consecutive failures")
                self.state = ConnectionState.FAILED
                self.recovery_start_time = datetime.now()
            elif self.state == ConnectionState.RECOVERING:
                self.recovery_attempts += 1
        else:
            self.state = ConnectionState.DEGRADED
        
        logger.error(f"Database {operation_type} operation failed: {error} (failure #{self.consecutive_failures})")
    
    def _classify_failure(self, error: Exception, operation_type: str) -> DatabaseFailureMode:
        """
        Classify the type of database failure.
        
        Args:
            error: The exception that occurred
            operation_type: Type of operation that failed
            
        Returns:
            DatabaseFailureMode: The classified failure mode
        """
        error_str = str(error).lower()
        
        # Check for read-only mode indicators
        if any(indicator in error_str for indicator in [
            'read-only', 'readonly', 'read only',
            'database is locked', 'disk full'
        ]):
            return DatabaseFailureMode.READ_ONLY
        
        # Check for write-only mode indicators (rare, but possible)
        if 'write' in operation_type.lower() and 'permission' in error_str:
            return DatabaseFailureMode.WRITE_ONLY
        
        # Default to full failure
        return DatabaseFailureMode.FULL_FAILURE
    
    def should_retry(self) -> bool:
        """
        Check if operation should be retried.
        
        Returns:
            bool: True if should retry, False otherwise
        """
        return self.retry_count < self.max_retries
    
    def can_perform_operation(self, operation_type: str) -> bool:
        """
        Check if a specific operation type can be performed given current state.
        
        Args:
            operation_type: Type of operation (read/write/connection)
            
        Returns:
            bool: True if operation can be performed, False otherwise
        """
        if self.state == ConnectionState.HEALTHY:
            return True
        
        if self.state == ConnectionState.FAILED:
            return False
        
        # Degraded state - check failure mode
        if self.failure_mode == DatabaseFailureMode.READ_ONLY:
            return operation_type.lower() in ['read', 'select', 'query']
        elif self.failure_mode == DatabaseFailureMode.WRITE_ONLY:
            return operation_type.lower() in ['write', 'insert', 'update', 'delete']
        
        return False
    
    def start_recovery(self):
        """Start the recovery process."""
        if self.state != ConnectionState.RECOVERING:
            logger.info("Starting database connection recovery")
            self.state = ConnectionState.RECOVERING
            self.recovery_start_time = datetime.now()
            self.recovery_attempts = 0
    
    def get_health_status(self) -> Dict[str, Any]:
        """
        Get current health status information.
        
        Returns:
            Dict containing health status details
        """
        now = datetime.now()
        
        status = {
            'state': self.state.value,
            'failure_mode': self.failure_mode.value if self.failure_mode else None,
            'consecutive_failures': self.consecutive_failures,
            'retry_count': self.retry_count,
            'last_success_time': self.last_success_time.isoformat(),
            'time_since_last_success': (now - self.last_success_time).total_seconds(),
        }
        
        if self.last_failure_time:
            status['last_failure_time'] = self.last_failure_time.isoformat()
            status['time_since_last_failure'] = (now - self.last_failure_time).total_seconds()
        
        if self.recovery_start_time:
            status['recovery_start_time'] = self.recovery_start_time.isoformat()
            status['recovery_duration'] = (now - self.recovery_start_time).total_seconds()
            status['recovery_attempts'] = self.recovery_attempts
        
        return status


class ResilientDatabaseManager:
    """
    Enhanced database manager with resilience and recovery capabilities.
    
    This class wraps the existing DatabaseManager with additional
    resilience features including exponential backoff, health monitoring,
    and graceful degradation.
    """
    
    def __init__(self, base_manager, health_monitor: Optional[ConnectionHealthMonitor] = None):
        """
        Initialize resilient database manager.
        
        Args:
            base_manager: The base DatabaseManager instance
            health_monitor: Optional health monitor (creates default if None)
        """
        self.base_manager = base_manager
        self.health_monitor = health_monitor or ConnectionHealthMonitor()
        
        # Operation retry configuration
        self.retry_operations = True
        self.circuit_breaker_enabled = True
        self.circuit_breaker_threshold = 10  # failures before opening circuit
        self.circuit_breaker_timeout = 60    # seconds before trying to close circuit
        
        # Circuit breaker state
        self.circuit_open = False
        self.circuit_open_time: Optional[datetime] = None
        self.circuit_failure_count = 0
    
    async def execute_with_resilience(
        self,
        operation: Callable[[], Awaitable[Any]],
        operation_type: str = "unknown",
        allow_partial_failure: bool = False
    ) -> Any:
        """
        Execute a database operation with resilience features.
        
        Args:
            operation: Async function to execute
            operation_type: Type of operation (for monitoring)
            allow_partial_failure: Whether to allow partial failures
            
        Returns:
            Operation result or None if failed
        """
        # Check circuit breaker
        if self.circuit_breaker_enabled and self._is_circuit_open():
            logger.warning(f"Circuit breaker open, skipping {operation_type} operation")
            return None
        
        # Check if operation can be performed in current state
        if not self.health_monitor.can_perform_operation(operation_type):
            logger.warning(f"Cannot perform {operation_type} operation in current state: {self.health_monitor.state.value}")
            if not allow_partial_failure:
                return None
        
        retry_count = 0
        last_error = None
        
        while retry_count <= self.health_monitor.max_retries:
            try:
                # Execute the operation
                result = await operation()
                
                # Record success
                self.health_monitor.record_success()
                self._reset_circuit_breaker()
                
                return result
                
            except Exception as e:
                last_error = e
                retry_count += 1
                
                # Record failure
                self.health_monitor.record_failure(e, operation_type)
                self._record_circuit_breaker_failure()
                
                # Check if we should retry
                if retry_count <= self.health_monitor.max_retries and self.retry_operations:
                    delay = self.health_monitor.calculate_backoff_delay()
                    logger.warning(f"Database operation failed, retrying in {delay:.2f}s (attempt {retry_count}/{self.health_monitor.max_retries})")
                    await asyncio.sleep(delay)
                else:
                    break
        
        # All retries exhausted
        logger.error(f"Database operation failed after {retry_count} attempts: {last_error}")
        
        # Open circuit breaker if threshold reached
        if self.circuit_failure_count >= self.circuit_breaker_threshold:
            self._open_circuit_breaker()
        
        return None
    
    def _is_circuit_open(self) -> bool:
        """Check if circuit breaker is open."""
        if not self.circuit_open:
            return False
        
        # Check if timeout has passed
        if self.circuit_open_time:
            time_open = (datetime.now() - self.circuit_open_time).total_seconds()
            if time_open >= self.circuit_breaker_timeout:
                logger.info("Circuit breaker timeout reached, attempting to close circuit")
                self.circuit_open = False
                self.circuit_open_time = None
                return False
        
        return True
    
    def _open_circuit_breaker(self):
        """Open the circuit breaker."""
        if not self.circuit_open:
            logger.warning(f"Opening circuit breaker after {self.circuit_failure_count} failures")
            self.circuit_open = True
            self.circuit_open_time = datetime.now()
    
    def _reset_circuit_breaker(self):
        """Reset circuit breaker on successful operation."""
        if self.circuit_open or self.circuit_failure_count > 0:
            logger.info("Resetting circuit breaker after successful operation")
            self.circuit_open = False
            self.circuit_open_time = None
            self.circuit_failure_count = 0
    
    def _record_circuit_breaker_failure(self):
        """Record a failure for circuit breaker tracking."""
        self.circuit_failure_count += 1
    
    # Wrap base manager methods with resilience
    async def store_message(self, message_event) -> bool:
        """Store message with resilience."""
        result = await self.execute_with_resilience(
            lambda: self.base_manager.store_message(message_event),
            operation_type="write",
            allow_partial_failure=False
        )
        return result is not None and result
    
    async def get_recent_messages(self, channel: str, limit: int = 200):
        """Get recent messages with resilience."""
        result = await self.execute_with_resilience(
            lambda: self.base_manager.get_recent_messages(channel, limit),
            operation_type="read",
            allow_partial_failure=True
        )
        return result if result is not None else []
    
    async def delete_message_by_id(self, message_id: str) -> bool:
        """Delete message by ID with resilience."""
        result = await self.execute_with_resilience(
            lambda: self.base_manager.delete_message_by_id(message_id),
            operation_type="write",
            allow_partial_failure=False
        )
        return result is not None and result
    
    async def delete_user_messages(self, channel: str, user_id: str) -> bool:
        """Delete user messages with resilience."""
        result = await self.execute_with_resilience(
            lambda: self.base_manager.delete_user_messages(channel, user_id),
            operation_type="write",
            allow_partial_failure=False
        )
        return result is not None and result
    
    async def clear_channel_messages(self, channel: str) -> bool:
        """Clear channel messages with resilience."""
        result = await self.execute_with_resilience(
            lambda: self.base_manager.clear_channel_messages(channel),
            operation_type="write",
            allow_partial_failure=False
        )
        return result is not None and result
    
    async def cleanup_old_messages(self, channel: str, retention_days: int = 7) -> bool:
        """Cleanup old messages with resilience."""
        result = await self.execute_with_resilience(
            lambda: self.base_manager.cleanup_old_messages(channel, retention_days),
            operation_type="write",
            allow_partial_failure=True
        )
        return result is not None and result
    
    async def count_recent_messages(self, channel: str, hours: int = 24) -> int:
        """Count recent messages with resilience."""
        result = await self.execute_with_resilience(
            lambda: self.base_manager.count_recent_messages(channel, hours),
            operation_type="read",
            allow_partial_failure=True
        )
        return result if result is not None else 0
    
    async def health_check(self) -> bool:
        """
        Perform a health check on the database connection.
        
        Returns:
            bool: True if healthy, False otherwise
        """
        try:
            # Simple query to test connection
            result = await self.execute_with_resilience(
                lambda: self.base_manager.fetch_all("SELECT 1 as test"),
                operation_type="read",
                allow_partial_failure=False
            )
            return result is not None
            
        except Exception as e:
            logger.error(f"Database health check failed: {e}")
            return False
    
    async def start_health_monitoring(self):
        """Start background health monitoring task."""
        asyncio.create_task(self._health_monitoring_loop())
    
    async def _health_monitoring_loop(self):
        """Background task for continuous health monitoring."""
        while True:
            try:
                await asyncio.sleep(self.health_monitor.health_check_interval)
                
                # Perform health check
                is_healthy = await self.health_check()
                
                if not is_healthy and self.health_monitor.state == ConnectionState.HEALTHY:
                    logger.warning("Database health check failed, starting recovery")
                    self.health_monitor.start_recovery()
                
                # Log health status periodically
                if self.health_monitor.consecutive_failures > 0:
                    status = self.health_monitor.get_health_status()
                    logger.info(f"Database health status: {status}")
                
            except Exception as e:
                logger.error(f"Health monitoring error: {e}")
    
    def get_health_status(self) -> Dict[str, Any]:
        """Get comprehensive health status."""
        status = self.health_monitor.get_health_status()
        status.update({
            'circuit_breaker_open': self.circuit_open,
            'circuit_failure_count': self.circuit_failure_count,
            'retry_operations_enabled': self.retry_operations,
        })
        
        if self.circuit_open_time:
            status['circuit_open_time'] = self.circuit_open_time.isoformat()
            status['circuit_open_duration'] = (datetime.now() - self.circuit_open_time).total_seconds()
        
        return status