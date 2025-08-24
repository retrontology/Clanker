"""
Resource management and cleanup for the Twitch Ollama Chatbot.

This module provides memory usage monitoring, automatic cleanup tasks,
and resource exhaustion protection with configurable thresholds.
"""

import asyncio
import psutil
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List
from dataclasses import dataclass

from .database.operations import DatabaseManager, ChannelConfigManager
from .logging.metrics import MetricsManager
from .logging.logger import get_logger


@dataclass
class ResourceThresholds:
    """Configuration for resource usage thresholds."""
    memory_warning_mb: int = 512  # MB
    memory_critical_mb: int = 1024  # MB
    disk_warning_percent: int = 85  # %
    disk_critical_percent: int = 95  # %
    message_retention_days: int = 30  # days
    metrics_retention_days: int = 7  # days
    cleanup_interval_minutes: int = 60  # minutes


@dataclass
class ResourceUsage:
    """Current resource usage information."""
    memory_mb: float
    memory_percent: float
    disk_usage_percent: float
    disk_free_gb: float
    cpu_percent: float
    timestamp: datetime


class ResourceManager:
    """
    Manager for memory usage monitoring, automatic cleanup, and resource protection.
    
    Features:
    - Memory usage monitoring with configurable thresholds
    - Automatic cleanup of old messages and metrics
    - Resource exhaustion protection
    - Periodic cleanup tasks
    - Performance monitoring integration
    """
    
    def __init__(
        self,
        db_manager: DatabaseManager,
        config_manager: ChannelConfigManager,
        metrics_manager: MetricsManager,
        thresholds: Optional[ResourceThresholds] = None
    ):
        """
        Initialize ResourceManager.
        
        Args:
            db_manager: Database manager instance
            config_manager: Channel configuration manager
            metrics_manager: Metrics manager instance
            thresholds: Resource threshold configuration
        """
        self.db_manager = db_manager
        self.config_manager = config_manager
        self.metrics_manager = metrics_manager
        self.thresholds = thresholds or ResourceThresholds()
        
        self.logger = get_logger("resource_manager")
        
        # Resource monitoring state
        self._monitoring_active = False
        self._cleanup_task: Optional[asyncio.Task] = None
        self._monitoring_task: Optional[asyncio.Task] = None
        
        # Resource usage history
        self._usage_history: List[ResourceUsage] = []
        self._max_history_size = 100
        
        # Cleanup statistics
        self._cleanup_stats = {
            'last_cleanup': None,
            'total_cleanups': 0,
            'messages_cleaned': 0,
            'metrics_cleaned': 0,
            'user_cooldowns_cleaned': 0
        }
        
        # Process reference for monitoring
        self._process = psutil.Process()
        
        self.logger.info(
            "ResourceManager initialized",
            memory_warning_mb=self.thresholds.memory_warning_mb,
            memory_critical_mb=self.thresholds.memory_critical_mb,
            cleanup_interval_minutes=self.thresholds.cleanup_interval_minutes
        )
    
    async def start_monitoring(self) -> None:
        """Start resource monitoring and cleanup tasks."""
        if self._monitoring_active:
            self.logger.warning("Resource monitoring already active")
            return
        
        self._monitoring_active = True
        
        # Start monitoring task
        self._monitoring_task = asyncio.create_task(self._monitor_resources())
        
        # Start cleanup task
        self._cleanup_task = asyncio.create_task(self._periodic_cleanup())
        
        self.logger.info("Resource monitoring and cleanup tasks started")
    
    async def stop_monitoring(self) -> None:
        """Stop resource monitoring and cleanup tasks."""
        self._monitoring_active = False
        
        # Cancel tasks
        if self._monitoring_task and not self._monitoring_task.done():
            self._monitoring_task.cancel()
            try:
                await self._monitoring_task
            except asyncio.CancelledError:
                pass
        
        if self._cleanup_task and not self._cleanup_task.done():
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
        
        self.logger.info("Resource monitoring stopped")
    
    async def _monitor_resources(self) -> None:
        """Monitor resource usage periodically."""
        while self._monitoring_active:
            try:
                # Get current resource usage
                usage = await self._get_resource_usage()
                
                # Add to history
                self._usage_history.append(usage)
                if len(self._usage_history) > self._max_history_size:
                    self._usage_history.pop(0)
                
                # Check thresholds and log warnings
                await self._check_resource_thresholds(usage)
                
                # Record metrics
                await self._record_resource_metrics(usage)
                
                # Wait before next check (every 30 seconds)
                await asyncio.sleep(30)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"Error in resource monitoring: {e}")
                await asyncio.sleep(30)  # Continue monitoring despite errors
    
    async def _periodic_cleanup(self) -> None:
        """Perform periodic cleanup tasks."""
        while self._monitoring_active:
            try:
                # Wait for cleanup interval
                await asyncio.sleep(self.thresholds.cleanup_interval_minutes * 60)
                
                if not self._monitoring_active:
                    break
                
                # Perform cleanup
                await self.cleanup_old_data()
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"Error in periodic cleanup: {e}")
    
    async def _get_resource_usage(self) -> ResourceUsage:
        """Get current resource usage information."""
        try:
            # Memory usage
            memory_info = self._process.memory_info()
            memory_mb = memory_info.rss / 1024 / 1024  # Convert to MB
            memory_percent = self._process.memory_percent()
            
            # CPU usage
            cpu_percent = self._process.cpu_percent()
            
            # Disk usage (for the current working directory)
            disk_usage = psutil.disk_usage('.')
            disk_usage_percent = (disk_usage.used / disk_usage.total) * 100
            disk_free_gb = disk_usage.free / 1024 / 1024 / 1024  # Convert to GB
            
            return ResourceUsage(
                memory_mb=memory_mb,
                memory_percent=memory_percent,
                disk_usage_percent=disk_usage_percent,
                disk_free_gb=disk_free_gb,
                cpu_percent=cpu_percent,
                timestamp=datetime.utcnow()
            )
            
        except Exception as e:
            self.logger.error(f"Error getting resource usage: {e}")
            # Return default values on error
            return ResourceUsage(
                memory_mb=0,
                memory_percent=0,
                disk_usage_percent=0,
                disk_free_gb=0,
                cpu_percent=0,
                timestamp=datetime.utcnow()
            )
    
    async def _check_resource_thresholds(self, usage: ResourceUsage) -> None:
        """Check resource usage against thresholds and log warnings."""
        # Memory threshold checks
        if usage.memory_mb >= self.thresholds.memory_critical_mb:
            self.logger.error(
                "Critical memory usage detected",
                memory_mb=usage.memory_mb,
                threshold_mb=self.thresholds.memory_critical_mb,
                memory_percent=usage.memory_percent
            )
            # Trigger emergency cleanup
            await self._emergency_cleanup()
            
        elif usage.memory_mb >= self.thresholds.memory_warning_mb:
            self.logger.warning(
                "High memory usage detected",
                memory_mb=usage.memory_mb,
                threshold_mb=self.thresholds.memory_warning_mb,
                memory_percent=usage.memory_percent
            )
        
        # Disk threshold checks
        if usage.disk_usage_percent >= self.thresholds.disk_critical_percent:
            self.logger.error(
                "Critical disk usage detected",
                disk_usage_percent=usage.disk_usage_percent,
                threshold_percent=self.thresholds.disk_critical_percent,
                disk_free_gb=usage.disk_free_gb
            )
            # Trigger emergency cleanup
            await self._emergency_cleanup()
            
        elif usage.disk_usage_percent >= self.thresholds.disk_warning_percent:
            self.logger.warning(
                "High disk usage detected",
                disk_usage_percent=usage.disk_usage_percent,
                threshold_percent=self.thresholds.disk_warning_percent,
                disk_free_gb=usage.disk_free_gb
            )
    
    async def _record_resource_metrics(self, usage: ResourceUsage) -> None:
        """Record resource usage metrics."""
        try:
            # Record system-wide metrics (use "system" as channel)
            await self.metrics_manager.record_response_time("system", usage.memory_mb)
            await self.metrics_manager._add_metric("system", "memory_usage_mb", usage.memory_mb)
            await self.metrics_manager._add_metric("system", "memory_usage_percent", usage.memory_percent)
            await self.metrics_manager._add_metric("system", "disk_usage_percent", usage.disk_usage_percent)
            await self.metrics_manager._add_metric("system", "cpu_usage_percent", usage.cpu_percent)
            
        except Exception as e:
            self.logger.error(f"Error recording resource metrics: {e}")
    
    async def _emergency_cleanup(self) -> None:
        """Perform emergency cleanup when resources are critically low."""
        self.logger.warning("Performing emergency cleanup due to resource exhaustion")
        
        try:
            # More aggressive cleanup with shorter retention periods
            emergency_message_retention = max(1, self.thresholds.message_retention_days // 4)  # 1/4 of normal retention
            emergency_metrics_retention = max(1, self.thresholds.metrics_retention_days // 2)  # 1/2 of normal retention
            
            # Clean up old messages more aggressively
            messages_cleaned = await self._cleanup_old_messages(emergency_message_retention)
            
            # Clean up old metrics more aggressively
            metrics_cleaned = await self.metrics_manager.cleanup_old_metrics(emergency_metrics_retention)
            
            # Clean up user cooldowns
            cooldowns_cleaned = await self._cleanup_old_user_cooldowns(emergency_message_retention)
            
            self.logger.info(
                "Emergency cleanup completed",
                messages_cleaned=messages_cleaned,
                metrics_cleaned=metrics_cleaned,
                cooldowns_cleaned=cooldowns_cleaned,
                retention_days_used=emergency_message_retention
            )
            
        except Exception as e:
            self.logger.error(f"Error during emergency cleanup: {e}")
    
    async def cleanup_old_data(self, force_cleanup: bool = False) -> Dict[str, int]:
        """
        Clean up old data (messages, metrics, temporary data).
        
        Args:
            force_cleanup: Force cleanup even if not due
            
        Returns:
            Dictionary with cleanup statistics
        """
        try:
            start_time = datetime.utcnow()
            
            # Check if cleanup is due (unless forced)
            if not force_cleanup and self._cleanup_stats['last_cleanup']:
                time_since_cleanup = start_time - self._cleanup_stats['last_cleanup']
                if time_since_cleanup.total_seconds() < (self.thresholds.cleanup_interval_minutes * 60):
                    self.logger.debug("Cleanup not due yet, skipping")
                    return {}
            
            self.logger.info("Starting data cleanup")
            
            # Clean up old messages
            messages_cleaned = await self._cleanup_old_messages(self.thresholds.message_retention_days)
            
            # Clean up old metrics
            metrics_cleaned = await self.metrics_manager.cleanup_old_metrics(self.thresholds.metrics_retention_days)
            
            # Clean up old user cooldowns
            cooldowns_cleaned = await self._cleanup_old_user_cooldowns(self.thresholds.message_retention_days)
            
            # Update cleanup statistics
            self._cleanup_stats.update({
                'last_cleanup': start_time,
                'total_cleanups': self._cleanup_stats['total_cleanups'] + 1,
                'messages_cleaned': self._cleanup_stats['messages_cleaned'] + messages_cleaned,
                'metrics_cleaned': self._cleanup_stats['metrics_cleaned'] + metrics_cleaned,
                'user_cooldowns_cleaned': self._cleanup_stats['user_cooldowns_cleaned'] + cooldowns_cleaned
            })
            
            cleanup_duration = (datetime.utcnow() - start_time).total_seconds()
            
            self.logger.info(
                "Data cleanup completed",
                messages_cleaned=messages_cleaned,
                metrics_cleaned=metrics_cleaned,
                cooldowns_cleaned=cooldowns_cleaned,
                duration_seconds=cleanup_duration,
                retention_days=self.thresholds.message_retention_days
            )
            
            return {
                'messages_cleaned': messages_cleaned,
                'metrics_cleaned': metrics_cleaned,
                'cooldowns_cleaned': cooldowns_cleaned,
                'duration_seconds': cleanup_duration
            }
            
        except Exception as e:
            self.logger.error(f"Error during data cleanup: {e}")
            return {'error': str(e)}
    
    async def _cleanup_old_messages(self, retention_days: int) -> int:
        """Clean up old messages from database."""
        try:
            cutoff_date = datetime.utcnow() - timedelta(days=retention_days)
            
            query = "DELETE FROM messages WHERE timestamp < ?"
            result = await self.db_manager.execute(query, (cutoff_date,))
            
            deleted_count = result.rowcount if hasattr(result, 'rowcount') else 0
            
            self.logger.debug(
                "Old messages cleaned up",
                deleted_count=deleted_count,
                retention_days=retention_days
            )
            
            return deleted_count
            
        except Exception as e:
            self.logger.error(f"Error cleaning up old messages: {e}")
            return 0
    
    async def _cleanup_old_user_cooldowns(self, retention_days: int) -> int:
        """Clean up old user response cooldowns."""
        try:
            cutoff_date = datetime.utcnow() - timedelta(days=retention_days)
            
            query = "DELETE FROM user_response_cooldowns WHERE last_response_time < ?"
            result = await self.db_manager.execute(query, (cutoff_date,))
            
            deleted_count = result.rowcount if hasattr(result, 'rowcount') else 0
            
            self.logger.debug(
                "Old user cooldowns cleaned up",
                deleted_count=deleted_count,
                retention_days=retention_days
            )
            
            return deleted_count
            
        except Exception as e:
            self.logger.error(f"Error cleaning up old user cooldowns: {e}")
            return 0
    
    def get_resource_status(self) -> Dict[str, Any]:
        """
        Get current resource status and statistics.
        
        Returns:
            Dictionary containing resource status information
        """
        try:
            current_usage = None
            if self._usage_history:
                current_usage = self._usage_history[-1]
            
            # Calculate average usage over last hour
            one_hour_ago = datetime.utcnow() - timedelta(hours=1)
            recent_usage = [
                usage for usage in self._usage_history
                if usage.timestamp >= one_hour_ago
            ]
            
            avg_memory_mb = 0
            avg_cpu_percent = 0
            if recent_usage:
                avg_memory_mb = sum(u.memory_mb for u in recent_usage) / len(recent_usage)
                avg_cpu_percent = sum(u.cpu_percent for u in recent_usage) / len(recent_usage)
            
            status = {
                'monitoring_active': self._monitoring_active,
                'thresholds': {
                    'memory_warning_mb': self.thresholds.memory_warning_mb,
                    'memory_critical_mb': self.thresholds.memory_critical_mb,
                    'disk_warning_percent': self.thresholds.disk_warning_percent,
                    'disk_critical_percent': self.thresholds.disk_critical_percent,
                    'cleanup_interval_minutes': self.thresholds.cleanup_interval_minutes
                },
                'cleanup_stats': dict(self._cleanup_stats),
                'usage_history_size': len(self._usage_history)
            }
            
            if current_usage:
                status['current_usage'] = {
                    'memory_mb': round(current_usage.memory_mb, 2),
                    'memory_percent': round(current_usage.memory_percent, 2),
                    'disk_usage_percent': round(current_usage.disk_usage_percent, 2),
                    'disk_free_gb': round(current_usage.disk_free_gb, 2),
                    'cpu_percent': round(current_usage.cpu_percent, 2),
                    'timestamp': current_usage.timestamp.isoformat()
                }
            
            if recent_usage:
                status['hourly_averages'] = {
                    'memory_mb': round(avg_memory_mb, 2),
                    'cpu_percent': round(avg_cpu_percent, 2),
                    'sample_count': len(recent_usage)
                }
            
            return status
            
        except Exception as e:
            self.logger.error(f"Error getting resource status: {e}")
            return {'error': str(e)}
    
    def is_resource_exhausted(self) -> bool:
        """
        Check if system resources are critically exhausted.
        
        Returns:
            bool: True if resources are critically low, False otherwise
        """
        if not self._usage_history:
            return False
        
        current_usage = self._usage_history[-1]
        
        # Check if memory or disk usage is critical
        memory_critical = current_usage.memory_mb >= self.thresholds.memory_critical_mb
        disk_critical = current_usage.disk_usage_percent >= self.thresholds.disk_critical_percent
        
        return memory_critical or disk_critical
    
    async def shutdown(self) -> None:
        """Shutdown resource manager and perform final cleanup."""
        self.logger.info("Shutting down resource manager")
        
        # Stop monitoring
        await self.stop_monitoring()
        
        # Perform final cleanup
        try:
            await self.cleanup_old_data(force_cleanup=True)
        except Exception as e:
            self.logger.error(f"Error during final cleanup: {e}")
        
        self.logger.info("Resource manager shutdown complete")