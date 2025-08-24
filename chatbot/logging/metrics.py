"""
Performance metrics and monitoring for the Twitch Ollama Chatbot.

Provides metrics collection, storage, and reporting functionality
for tracking response times, success rates, and error counts.
"""

import asyncio
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
from dataclasses import dataclass

from ..database.operations import DatabaseManager
from .logger import get_logger


@dataclass
class MetricData:
    """Data class for metric information."""
    channel: str
    metric_type: str
    metric_value: float
    timestamp: datetime


class MetricsManager:
    """
    Manager for collecting and storing performance metrics.
    
    Tracks:
    - Response times for Ollama API calls
    - Success/failure rates for message generation
    - Error counts by type and channel
    - System performance metrics
    """
    
    def __init__(self, db_manager: DatabaseManager):
        """
        Initialize metrics manager.
        
        Args:
            db_manager: Database manager instance for metric storage
        """
        self.db = db_manager
        self.logger = get_logger("metrics")
        
        # In-memory metric buffers for batch processing
        self._metric_buffer: List[MetricData] = []
        self._buffer_lock = asyncio.Lock()
        self._flush_task: Optional[asyncio.Task] = None
        
        # Metric counters for current session
        self._session_metrics: Dict[str, Dict[str, float]] = {}
        
        # Start background flush task
        self._start_flush_task()
    
    def _start_flush_task(self):
        """Start background task to flush metrics to database."""
        if self._flush_task is None or self._flush_task.done():
            self._flush_task = asyncio.create_task(self._flush_metrics_periodically())
    
    async def _flush_metrics_periodically(self):
        """Periodically flush metrics buffer to database."""
        while True:
            try:
                await asyncio.sleep(60)  # Flush every minute
                await self._flush_metrics_buffer()
            except asyncio.CancelledError:
                # Final flush before shutdown
                await self._flush_metrics_buffer()
                break
            except Exception as e:
                self.logger.error("Error in metrics flush task", error=str(e))
    
    async def _flush_metrics_buffer(self):
        """Flush metrics buffer to database."""
        async with self._buffer_lock:
            if not self._metric_buffer:
                return
            
            try:
                # Batch insert metrics
                await self._store_metrics_batch(self._metric_buffer)
                self.logger.debug(f"Flushed {len(self._metric_buffer)} metrics to database")
                self._metric_buffer.clear()
            except Exception as e:
                self.logger.error("Failed to flush metrics to database", error=str(e))
    
    async def _store_metrics_batch(self, metrics: List[MetricData]):
        """Store a batch of metrics in the database."""
        query = """
        INSERT INTO bot_metrics (channel, metric_type, metric_value, timestamp)
        VALUES (?, ?, ?, ?)
        """
        
        values = [
            (metric.channel, metric.metric_type, metric.metric_value, metric.timestamp)
            for metric in metrics
        ]
        
        await self.db.execute_many(query, values)
    
    async def _add_metric(self, channel: str, metric_type: str, value: float):
        """Add a metric to the buffer."""
        metric = MetricData(
            channel=channel,
            metric_type=metric_type,
            metric_value=value,
            timestamp=datetime.utcnow()
        )
        
        async with self._buffer_lock:
            self._metric_buffer.append(metric)
        
        # Update session metrics
        if channel not in self._session_metrics:
            self._session_metrics[channel] = {}
        
        if metric_type not in self._session_metrics[channel]:
            self._session_metrics[channel][metric_type] = 0
        
        self._session_metrics[channel][metric_type] += value
    
    async def record_response_time(self, channel: str, duration_ms: float):
        """
        Record Ollama API response time.
        
        Args:
            channel: Channel name
            duration_ms: Response time in milliseconds
        """
        await self._add_metric(channel, "response_time", duration_ms)
        
        self.logger.debug(
            "Recorded response time",
            channel=channel,
            duration_ms=duration_ms
        )
    
    async def record_success(self, channel: str, operation_type: str = "generation"):
        """
        Record successful operation.
        
        Args:
            channel: Channel name
            operation_type: Type of operation (generation, response, etc.)
        """
        metric_type = f"{operation_type}_success"
        await self._add_metric(channel, metric_type, 1.0)
        
        self.logger.debug(
            "Recorded success",
            channel=channel,
            operation_type=operation_type
        )
    
    async def record_error(self, channel: str, error_type: str, operation_type: str = "generation"):
        """
        Record error occurrence.
        
        Args:
            channel: Channel name
            error_type: Type of error (timeout, api_error, filter_block, etc.)
            operation_type: Type of operation that failed
        """
        metric_type = f"{operation_type}_error_{error_type}"
        await self._add_metric(channel, metric_type, 1.0)
        
        self.logger.warning(
            "Recorded error",
            channel=channel,
            error_type=error_type,
            operation_type=operation_type
        )
    
    async def record_message_count(self, channel: str, count: int):
        """
        Record message count for a channel.
        
        Args:
            channel: Channel name
            count: Number of messages processed
        """
        await self._add_metric(channel, "messages_processed", float(count))
    
    async def record_filter_block(self, channel: str, filter_type: str):
        """
        Record content filter block.
        
        Args:
            channel: Channel name
            filter_type: Type of filter that blocked content (input/output)
        """
        metric_type = f"filter_block_{filter_type}"
        await self._add_metric(channel, metric_type, 1.0)
        
        self.logger.info(
            "Recorded filter block",
            channel=channel,
            filter_type=filter_type
        )
    
    async def record_rate_limit_hit(self, channel: str, limit_type: str):
        """
        Record rate limit hit.
        
        Args:
            channel: Channel name
            limit_type: Type of rate limit (spontaneous, response)
        """
        metric_type = f"rate_limit_{limit_type}"
        await self._add_metric(channel, metric_type, 1.0)
        
        self.logger.debug(
            "Recorded rate limit hit",
            channel=channel,
            limit_type=limit_type
        )
    
    async def get_performance_stats(
        self,
        channel: Optional[str] = None,
        hours: int = 24
    ) -> Dict[str, Any]:
        """
        Get performance statistics for a channel or all channels.
        
        Args:
            channel: Channel name (None for all channels)
            hours: Number of hours to look back
        
        Returns:
            Dictionary containing performance statistics
        """
        since = datetime.utcnow() - timedelta(hours=hours)
        
        # Build query
        if channel:
            query = """
            SELECT metric_type, AVG(metric_value) as avg_value, 
                   COUNT(*) as count, SUM(metric_value) as total_value
            FROM bot_metrics 
            WHERE channel = ? AND timestamp >= ?
            GROUP BY metric_type
            """
            params = (channel, since)
        else:
            query = """
            SELECT channel, metric_type, AVG(metric_value) as avg_value,
                   COUNT(*) as count, SUM(metric_value) as total_value
            FROM bot_metrics 
            WHERE timestamp >= ?
            GROUP BY channel, metric_type
            """
            params = (since,)
        
        try:
            results = await self.db.fetch_all(query, params)
            
            if channel:
                # Single channel stats
                stats = {
                    "channel": channel,
                    "period_hours": hours,
                    "metrics": {}
                }
                
                for row in results:
                    metric_type = row["metric_type"]
                    stats["metrics"][metric_type] = {
                        "average": round(row["avg_value"], 2),
                        "count": row["count"],
                        "total": round(row["total_value"], 2)
                    }
                
                # Calculate derived metrics
                stats["derived"] = self._calculate_derived_metrics(stats["metrics"])
                
            else:
                # Multi-channel stats
                stats = {
                    "period_hours": hours,
                    "channels": {}
                }
                
                for row in results:
                    ch = row["channel"]
                    metric_type = row["metric_type"]
                    
                    if ch not in stats["channels"]:
                        stats["channels"][ch] = {"metrics": {}}
                    
                    stats["channels"][ch]["metrics"][metric_type] = {
                        "average": round(row["avg_value"], 2),
                        "count": row["count"],
                        "total": round(row["total_value"], 2)
                    }
                
                # Calculate derived metrics for each channel
                for ch in stats["channels"]:
                    stats["channels"][ch]["derived"] = self._calculate_derived_metrics(
                        stats["channels"][ch]["metrics"]
                    )
            
            return stats
            
        except Exception as e:
            self.logger.error("Failed to get performance stats", error=str(e))
            return {"error": str(e)}
    
    def _calculate_derived_metrics(self, metrics: Dict[str, Dict[str, float]]) -> Dict[str, float]:
        """Calculate derived metrics from raw metrics."""
        derived = {}
        
        # Success rate calculation
        total_success = sum(
            data["total"] for key, data in metrics.items()
            if key.endswith("_success")
        )
        total_errors = sum(
            data["total"] for key, data in metrics.items()
            if "_error_" in key
        )
        
        if total_success + total_errors > 0:
            derived["success_rate"] = round(
                total_success / (total_success + total_errors) * 100, 2
            )
        
        # Average response time
        if "response_time" in metrics:
            derived["avg_response_time_ms"] = metrics["response_time"]["average"]
        
        # Messages per hour
        if "messages_processed" in metrics:
            derived["messages_per_hour"] = round(
                metrics["messages_processed"]["total"], 2
            )
        
        return derived
    
    async def get_session_stats(self) -> Dict[str, Any]:
        """Get current session statistics."""
        return {
            "session_metrics": dict(self._session_metrics),
            "buffer_size": len(self._metric_buffer),
            "flush_task_running": self._flush_task and not self._flush_task.done()
        }
    
    async def cleanup_old_metrics(self, retention_days: int = 7):
        """
        Clean up old metrics from the database.
        
        Args:
            retention_days: Number of days to retain metrics
        """
        cutoff_date = datetime.utcnow() - timedelta(days=retention_days)
        
        query = "DELETE FROM bot_metrics WHERE timestamp < ?"
        
        try:
            result = await self.db.execute(query, (cutoff_date,))
            deleted_count = result.rowcount if hasattr(result, 'rowcount') else 0
            
            self.logger.info(
                "Cleaned up old metrics",
                deleted_count=deleted_count,
                retention_days=retention_days
            )
            
            return deleted_count
            
        except Exception as e:
            self.logger.error("Failed to cleanup old metrics", error=str(e))
            return 0
    
    async def shutdown(self):
        """Shutdown metrics manager and flush remaining metrics."""
        self.logger.info("Shutting down metrics manager")
        
        # Cancel flush task
        if self._flush_task and not self._flush_task.done():
            self._flush_task.cancel()
            try:
                await self._flush_task
            except asyncio.CancelledError:
                pass
        
        # Final flush
        await self._flush_metrics_buffer()
        
        self.logger.info("Metrics manager shutdown complete")