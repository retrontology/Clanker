"""
Ollama API client implementation.

This module handles communication with the Ollama API
for message generation and model management.
"""

import asyncio
import aiohttp
import json
import logging
import re
from typing import List, Optional, Dict, Any, Callable, Awaitable
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum

from ..database.models import Message


logger = logging.getLogger(__name__)


class OllamaServiceState(Enum):
    """Ollama service states."""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNAVAILABLE = "unavailable"
    RECOVERING = "recovering"


@dataclass
class GenerationRequest:
    """Request parameters for message generation."""
    model: str
    context_messages: List[str]
    user_input: Optional[str] = None
    max_length: int = 500


class OllamaError(Exception):
    """Base exception for Ollama-related errors."""
    pass


class OllamaTimeoutError(OllamaError):
    """Raised when Ollama API request times out."""
    pass


class OllamaModelError(OllamaError):
    """Raised when model is not available or invalid."""
    pass


class OllamaUnavailableError(OllamaError):
    """Raised when Ollama service is unavailable."""
    pass


class OllamaResilienceMonitor:
    """
    Monitors Ollama service health and manages graceful degradation.
    """
    
    def __init__(self, max_failures: int = 3, recovery_timeout: int = 300):
        """
        Initialize Ollama resilience monitor.
        
        Args:
            max_failures: Maximum consecutive failures before marking as unavailable
            recovery_timeout: Time to wait before attempting recovery (seconds)
        """
        self.max_failures = max_failures
        self.recovery_timeout = recovery_timeout
        
        self.state = OllamaServiceState.HEALTHY
        self.consecutive_failures = 0
        self.last_success_time = datetime.now()
        self.last_failure_time: Optional[datetime] = None
        self.unavailable_since: Optional[datetime] = None
        
        # Model validation cache
        self.validated_models: Dict[str, bool] = {}
        self.model_validation_time: Dict[str, datetime] = {}
        self.model_cache_ttl = 300  # 5 minutes
    
    def record_success(self):
        """Record a successful Ollama operation."""
        if self.state != OllamaServiceState.HEALTHY:
            logger.info(f"Ollama service recovered after {self.consecutive_failures} failures")
        
        self.state = OllamaServiceState.HEALTHY
        self.consecutive_failures = 0
        self.last_success_time = datetime.now()
        self.unavailable_since = None
    
    def record_failure(self, error: Exception, operation: str = "unknown"):
        """
        Record a failed Ollama operation.
        
        Args:
            error: The exception that occurred
            operation: Type of operation that failed
        """
        self.last_failure_time = datetime.now()
        self.consecutive_failures += 1
        
        # Classify the failure
        if isinstance(error, (OllamaTimeoutError, asyncio.TimeoutError)):
            logger.warning(f"Ollama {operation} operation timed out (failure #{self.consecutive_failures})")
        elif isinstance(error, OllamaModelError):
            logger.error(f"Ollama model error in {operation}: {error}")
        elif isinstance(error, (aiohttp.ClientError, ConnectionError)):
            logger.warning(f"Ollama connection error in {operation}: {error}")
        else:
            logger.error(f"Ollama {operation} operation failed: {error}")
        
        # Update state based on failure count
        if self.consecutive_failures >= self.max_failures:
            if self.state != OllamaServiceState.UNAVAILABLE:
                logger.error(f"Marking Ollama as unavailable after {self.consecutive_failures} consecutive failures")
                self.state = OllamaServiceState.UNAVAILABLE
                self.unavailable_since = datetime.now()
        elif self.consecutive_failures > 1:
            self.state = OllamaServiceState.DEGRADED
    
    def is_available(self) -> bool:
        """
        Check if Ollama service is available for operations.
        
        Returns:
            bool: True if available, False otherwise
        """
        if self.state == OllamaServiceState.HEALTHY:
            return True
        
        if self.state == OllamaServiceState.UNAVAILABLE:
            # Check if recovery timeout has passed
            if self.unavailable_since:
                time_unavailable = (datetime.now() - self.unavailable_since).total_seconds()
                if time_unavailable >= self.recovery_timeout:
                    logger.info("Ollama recovery timeout reached, attempting to recover")
                    self.state = OllamaServiceState.RECOVERING
                    return True
            return False
        
        # DEGRADED or RECOVERING state - allow operations but with caution
        return True
    
    def should_skip_generation(self) -> bool:
        """
        Check if message generation should be skipped due to service state.
        
        Returns:
            bool: True if should skip, False otherwise
        """
        return not self.is_available()
    
    def is_model_validated(self, model: str) -> Optional[bool]:
        """
        Check if model has been recently validated.
        
        Args:
            model: Model name to check
            
        Returns:
            bool: True if valid, False if invalid, None if not cached or expired
        """
        if model not in self.validated_models:
            return None
        
        validation_time = self.model_validation_time.get(model)
        if not validation_time:
            return None
        
        # Check if cache has expired
        age = (datetime.now() - validation_time).total_seconds()
        if age > self.model_cache_ttl:
            # Remove expired cache entry
            del self.validated_models[model]
            del self.model_validation_time[model]
            return None
        
        return self.validated_models[model]
    
    def cache_model_validation(self, model: str, is_valid: bool):
        """
        Cache model validation result.
        
        Args:
            model: Model name
            is_valid: Whether the model is valid
        """
        self.validated_models[model] = is_valid
        self.model_validation_time[model] = datetime.now()
    
    def get_status(self) -> Dict[str, Any]:
        """
        Get current service status.
        
        Returns:
            Dict containing status information
        """
        now = datetime.now()
        status = {
            'state': self.state.value,
            'consecutive_failures': self.consecutive_failures,
            'last_success_time': self.last_success_time.isoformat(),
            'time_since_last_success': (now - self.last_success_time).total_seconds(),
        }
        
        if self.last_failure_time:
            status['last_failure_time'] = self.last_failure_time.isoformat()
            status['time_since_last_failure'] = (now - self.last_failure_time).total_seconds()
        
        if self.unavailable_since:
            status['unavailable_since'] = self.unavailable_since.isoformat()
            status['unavailable_duration'] = (now - self.unavailable_since).total_seconds()
            status['recovery_timeout'] = self.recovery_timeout
        
        status['validated_models'] = list(self.validated_models.keys())
        
        return status


class OllamaClient:
    """
    HTTP client for Ollama API with timeout handling and error recovery.
    
    Handles both spontaneous message generation and mention responses
    with appropriate prompt formatting for each use case.
    """
    
    # System prompts for different generation types
    SPONTANEOUS_PROMPT = (
        "Generate a single casual chat message that fits naturally with the recent conversation. "
        "Be conversational and match the tone of recent messages. Don't reference specific users "
        "or respond to anyone directly - just add to the conversation naturally. Keep it under "
        "500 characters and avoid special formatting. Generate only the message content, nothing else."
    )
    
    RESPONSE_PROMPT = (
        "Generate a single casual response to the user's message, considering the recent chat context. "
        "Be conversational and match the tone of the chat. Address the user's input naturally but "
        "don't be overly formal. Keep it under 500 characters and avoid special formatting. "
        "Generate only the response content, nothing else."
    )
    
    def __init__(self, base_url: str, timeout: int = 30):
        """
        Initialize Ollama client.
        
        Args:
            base_url: Base URL for Ollama API (e.g., "http://localhost:11434")
            timeout: Request timeout in seconds
        """
        self.base_url = base_url.rstrip('/')
        self.timeout = timeout
        self._session: Optional[aiohttp.ClientSession] = None
        
        # Resilience monitoring
        self.resilience_monitor = OllamaResilienceMonitor()
        self.silent_failure_mode = True  # Fail silently when unavailable
        
    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create HTTP session."""
        if self._session is None or self._session.closed:
            timeout = aiohttp.ClientTimeout(total=self.timeout)
            self._session = aiohttp.ClientSession(timeout=timeout)
        return self._session
    
    async def close(self):
        """Close HTTP session."""
        if self._session and not self._session.closed:
            await self._session.close()
    
    async def _make_request(self, endpoint: str, data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Make HTTP request to Ollama API with error handling.
        
        Args:
            endpoint: API endpoint (e.g., "/api/generate")
            data: Request payload
            
        Returns:
            Response data as dictionary
            
        Raises:
            OllamaTimeoutError: If request times out
            OllamaError: For other API errors
        """
        session = await self._get_session()
        url = f"{self.base_url}{endpoint}"
        
        try:
            if data:
                async with session.post(url, json=data) as response:
                    if response.status == 200:
                        return await response.json()
                    else:
                        error_text = await response.text()
                        raise OllamaError(f"API request failed with status {response.status}: {error_text}")
            else:
                async with session.get(url) as response:
                    if response.status == 200:
                        return await response.json()
                    else:
                        error_text = await response.text()
                        raise OllamaError(f"API request failed with status {response.status}: {error_text}")
                        
        except asyncio.TimeoutError:
            logger.warning("Ollama API request timed out", extra={
                "endpoint": endpoint,
                "timeout": self.timeout
            })
            raise OllamaTimeoutError(f"Request to {endpoint} timed out after {self.timeout}s")
        except aiohttp.ClientError as e:
            logger.error("Ollama API client error", extra={
                "endpoint": endpoint,
                "error": str(e)
            })
            raise OllamaError(f"Client error: {str(e)}")
    
    async def list_available_models(self) -> List[str]:
        """
        Get list of available models from Ollama.
        
        Returns:
            List of model names
            
        Raises:
            OllamaError: If unable to retrieve models
        """
        try:
            response = await self._make_request("/api/tags")
            models = response.get("models", [])
            return [model["name"] for model in models]
        except Exception as e:
            logger.error("Failed to list Ollama models", extra={"error": str(e)})
            raise OllamaError(f"Failed to list models: {str(e)}")
    
    async def validate_model(self, model: str) -> bool:
        """
        Check if a model is available on the Ollama server.
        
        Args:
            model: Model name to validate
            
        Returns:
            True if model is available, False otherwise
        """
        # Check cache first
        cached_result = self.resilience_monitor.is_model_validated(model)
        if cached_result is not None:
            return cached_result
        
        try:
            available_models = await self.list_available_models()
            is_valid = model in available_models
            
            # Cache the result
            self.resilience_monitor.cache_model_validation(model, is_valid)
            
            if is_valid:
                self.resilience_monitor.record_success()
            
            return is_valid
            
        except Exception as e:
            self.resilience_monitor.record_failure(e, "model_validation")
            logger.warning("Could not validate model availability", extra={
                "model": model,
                "error": str(e)
            })
            return False
    
    async def validate_startup_model(self, model: str) -> None:
        """
        Validate that a model is available at startup.
        
        Args:
            model: Model name to validate
            
        Raises:
            OllamaModelError: If model is not available
        """
        try:
            # Check if Ollama is available first
            if not await self.is_service_available():
                raise OllamaModelError(f"Ollama service is not available at {self.base_url}")
            
            if not await self.validate_model(model):
                try:
                    available_models = await self.list_available_models()
                    raise OllamaModelError(
                        f"Model '{model}' is not available. Available models: {', '.join(available_models)}"
                    )
                except Exception:
                    raise OllamaModelError(
                        f"Model '{model}' is not available and could not retrieve available models"
                    )
        except OllamaModelError:
            raise
        except Exception as e:
            raise OllamaModelError(f"Failed to validate startup model '{model}': {str(e)}")
    
    async def is_service_available(self) -> bool:
        """
        Check if Ollama service is available.
        
        Returns:
            bool: True if service is available, False otherwise
        """
        if not self.resilience_monitor.is_available():
            return False
        
        try:
            # Simple health check - try to list models
            await self.list_available_models()
            self.resilience_monitor.record_success()
            return True
            
        except Exception as e:
            self.resilience_monitor.record_failure(e, "health_check")
            return False
    
    async def validate_model_for_command(self, model: str) -> tuple[bool, str]:
        """
        Validate model for chat command with user-friendly error message.
        
        Args:
            model: Model name to validate
            
        Returns:
            Tuple of (is_valid, error_message)
        """
        try:
            # Check service availability first
            if not await self.is_service_available():
                return False, "Ollama service is currently unavailable"
            
            # Check model validity
            if await self.validate_model(model):
                return True, ""
            else:
                try:
                    available_models = await self.list_available_models()
                    if available_models:
                        return False, f"Model '{model}' not found. Available: {', '.join(available_models[:5])}"
                    else:
                        return False, f"Model '{model}' not found and no models are available"
                except Exception:
                    return False, f"Model '{model}' not found (could not list available models)"
                    
        except Exception as e:
            logger.error(f"Error validating model for command: {e}")
            return False, "Error checking model availability"
    
    def should_skip_generation(self) -> bool:
        """
        Check if message generation should be skipped due to service unavailability.
        
        Returns:
            bool: True if should skip generation, False otherwise
        """
        return self.resilience_monitor.should_skip_generation()
    
    async def generate_with_fallback(self, operation: Callable[[], Awaitable[str]], 
                                   operation_name: str = "generation") -> Optional[str]:
        """
        Execute generation operation with graceful failure handling.
        
        Args:
            operation: Async function that performs the generation
            operation_name: Name of the operation for logging
            
        Returns:
            Generated message or None if failed/skipped
        """
        # Check if we should skip generation
        if self.should_skip_generation():
            if self.silent_failure_mode:
                logger.debug(f"Skipping {operation_name} - Ollama service unavailable")
                return None
            else:
                raise OllamaUnavailableError("Ollama service is unavailable")
        
        try:
            result = await operation()
            self.resilience_monitor.record_success()
            return result
            
        except (OllamaTimeoutError, asyncio.TimeoutError) as e:
            self.resilience_monitor.record_failure(e, operation_name)
            if self.silent_failure_mode:
                logger.warning(f"Ollama {operation_name} timed out, skipping silently")
                return None
            else:
                raise
                
        except (OllamaError, aiohttp.ClientError, ConnectionError) as e:
            self.resilience_monitor.record_failure(e, operation_name)
            if self.silent_failure_mode:
                logger.warning(f"Ollama {operation_name} failed, skipping silently: {e}")
                return None
            else:
                raise
                
        except Exception as e:
            self.resilience_monitor.record_failure(e, operation_name)
            logger.error(f"Unexpected error in Ollama {operation_name}: {e}")
            if self.silent_failure_mode:
                return None
            else:
                raise OllamaError(f"Unexpected error: {str(e)}")
    
    def get_service_status(self) -> Dict[str, Any]:
        """
        Get comprehensive service status information.
        
        Returns:
            Dict containing service status details
        """
        status = self.resilience_monitor.get_status()
        status.update({
            'base_url': self.base_url,
            'timeout': self.timeout,
            'silent_failure_mode': self.silent_failure_mode,
        })
        return status
    
    def format_context_for_spontaneous(self, messages: List[Message]) -> str:
        """
        Format chat context for spontaneous message generation.
        
        Args:
            messages: List of recent messages
            
        Returns:
            Formatted context string
        """
        if not messages:
            return "Recent chat messages:\n(No recent messages)\n\nGenerate a natural chat message."
        
        context_lines = ["Recent chat messages:"]
        for msg in messages[-20:]:  # Use last 20 messages for context
            context_lines.append(f"[{msg.user_display_name}]: {msg.message_content}")
        
        context_lines.append("\nGenerate a natural chat message that fits the conversation.")
        return "\n".join(context_lines)
    
    def format_context_for_response(self, messages: List[Message], user_input: str, user_name: str) -> str:
        """
        Format chat context for mention response generation.
        
        Args:
            messages: List of recent messages
            user_input: The user's message that mentioned the bot
            user_name: Display name of the user who mentioned the bot
            
        Returns:
            Formatted context string
        """
        context_lines = ["Recent chat messages:"]
        
        if messages:
            for msg in messages[-15:]:  # Use last 15 messages for context
                context_lines.append(f"[{msg.user_display_name}]: {msg.message_content}")
        else:
            context_lines.append("(No recent messages)")
        
        context_lines.append(f"\nGenerate a response to {user_name}'s message: \"{user_input}\"")
        return "\n".join(context_lines)
    
    def validate_response(self, response: str) -> str:
        """
        Validate and format AI response.
        
        Args:
            response: Raw response from Ollama
            
        Returns:
            Cleaned and validated response
            
        Raises:
            OllamaError: If response is invalid or empty
        """
        if not response or not response.strip():
            raise OllamaError("Empty response from Ollama")
        
        # Clean the response
        cleaned = response.strip()
        
        # Remove any markdown formatting
        cleaned = re.sub(r'\*\*(.*?)\*\*', r'\1', cleaned)  # Bold
        cleaned = re.sub(r'\*(.*?)\*', r'\1', cleaned)      # Italic
        cleaned = re.sub(r'`(.*?)`', r'\1', cleaned)        # Code
        cleaned = re.sub(r'~~(.*?)~~', r'\1', cleaned)      # Strikethrough
        
        # Remove any special characters that Twitch doesn't support well
        cleaned = re.sub(r'[^\w\s\.,!?;:()\-\'\"@#$%&+=<>/\\]', '', cleaned)
        
        # Handle multiple lines - take first non-empty line
        lines = [line.strip() for line in cleaned.split('\n') if line.strip()]
        if not lines:
            raise OllamaError("No valid content in response")
        
        final_response = lines[0]
        
        # Enforce 500 character limit with intelligent truncation
        if len(final_response) > 500:
            # Try to truncate at word boundary
            truncated = final_response[:497]
            last_space = truncated.rfind(' ')
            if last_space > 400:  # Only truncate at word if we don't lose too much
                final_response = truncated[:last_space] + "..."
            else:
                final_response = truncated + "..."
        
        return final_response
    
    async def _generate_message(self, model: str, prompt: str, context: str) -> str:
        """
        Generate message using Ollama API.
        
        Args:
            model: Model name to use
            prompt: System prompt
            context: Formatted context
            
        Returns:
            Generated message
            
        Raises:
            OllamaError: If generation fails
        """
        full_prompt = f"{prompt}\n\n{context}"
        
        request_data = {
            "model": model,
            "prompt": full_prompt,
            "stream": False,
            "options": {
                "temperature": 0.8,
                "top_p": 0.9,
                "max_tokens": 150  # Limit tokens to help stay under 500 chars
            }
        }
        
        start_time = datetime.now()
        try:
            response = await self._make_request("/api/generate", request_data)
            duration = (datetime.now() - start_time).total_seconds() * 1000
            
            if "response" not in response:
                raise OllamaError("Invalid response format from Ollama")
            
            generated_text = response["response"]
            validated_response = self.validate_response(generated_text)
            
            logger.info("Generated message successfully", extra={
                "model": model,
                "response_time_ms": duration,
                "response_length": len(validated_response)
            })
            
            return validated_response
            
        except (OllamaTimeoutError, OllamaError):
            raise
        except Exception as e:
            duration = (datetime.now() - start_time).total_seconds() * 1000
            logger.error("Message generation failed", extra={
                "model": model,
                "error": str(e),
                "response_time_ms": duration
            })
            raise OllamaError(f"Generation failed: {str(e)}")
    
    async def generate_spontaneous_message(self, model: str, context: List[Message]) -> Optional[str]:
        """
        Generate a spontaneous chat message with resilience.
        
        Args:
            model: Ollama model to use
            context: List of recent messages for context
            
        Returns:
            Generated message or None if failed/skipped
        """
        async def _generate():
            formatted_context = self.format_context_for_spontaneous(context)
            return await self._generate_message(model, self.SPONTANEOUS_PROMPT, formatted_context)
        
        return await self.generate_with_fallback(_generate, "spontaneous_generation")
    
    async def generate_response_message(self, model: str, context: List[Message], 
                                      user_input: str, user_name: str) -> Optional[str]:
        """
        Generate a response to a user mention with resilience.
        
        Args:
            model: Ollama model to use
            context: List of recent messages for context
            user_input: The user's message that mentioned the bot
            user_name: Display name of the user
            
        Returns:
            Generated response or None if failed/skipped
        """
        async def _generate():
            formatted_context = self.format_context_for_response(context, user_input, user_name)
            return await self._generate_message(model, self.RESPONSE_PROMPT, formatted_context)
        
        return await self.generate_with_fallback(_generate, "response_generation")
    
    async def generate_spontaneous_message_strict(self, model: str, context: List[Message]) -> str:
        """
        Generate a spontaneous chat message with strict error handling (raises exceptions).
        
        Args:
            model: Ollama model to use
            context: List of recent messages for context
            
        Returns:
            Generated message
            
        Raises:
            OllamaError: If generation fails
        """
        formatted_context = self.format_context_for_spontaneous(context)
        return await self._generate_message(model, self.SPONTANEOUS_PROMPT, formatted_context)
    
    async def generate_response_message_strict(self, model: str, context: List[Message], 
                                             user_input: str, user_name: str) -> str:
        """
        Generate a response to a user mention with strict error handling (raises exceptions).
        
        Args:
            model: Ollama model to use
            context: List of recent messages for context
            user_input: The user's message that mentioned the bot
            user_name: Display name of the user
            
        Returns:
            Generated response
            
        Raises:
            OllamaError: If generation fails
        """
        formatted_context = self.format_context_for_response(context, user_input, user_name)
        return await self._generate_message(model, self.RESPONSE_PROMPT, formatted_context)