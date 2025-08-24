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
from typing import List, Optional, Dict, Any
from dataclasses import dataclass
from datetime import datetime

from ..database.models import Message


logger = logging.getLogger(__name__)


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
        try:
            available_models = await self.list_available_models()
            return model in available_models
        except Exception as e:
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
            if not await self.validate_model(model):
                available_models = await self.list_available_models()
                raise OllamaModelError(
                    f"Model '{model}' is not available. Available models: {', '.join(available_models)}"
                )
        except OllamaModelError:
            raise
        except Exception as e:
            raise OllamaModelError(f"Failed to validate startup model '{model}': {str(e)}")
    
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
    
    async def generate_spontaneous_message(self, model: str, context: List[Message]) -> str:
        """
        Generate a spontaneous chat message.
        
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
    
    async def generate_response_message(self, model: str, context: List[Message], 
                                      user_input: str, user_name: str) -> str:
        """
        Generate a response to a user mention.
        
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