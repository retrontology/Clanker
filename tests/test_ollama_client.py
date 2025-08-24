"""
Unit tests for OllamaClient.

Tests Ollama API communication, message generation, and error handling.
"""

import pytest
import asyncio
import aiohttp
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from datetime import datetime

from chatbot.ollama.client import (
    OllamaClient, OllamaError, OllamaTimeoutError, OllamaModelError, 
    OllamaUnavailableError, OllamaResilienceMonitor, OllamaServiceState
)
from chatbot.database.models import Message
from tests.conftest import create_test_message


class TestOllamaClient:
    """Test cases for OllamaClient class."""
    
    def test_initialization(self):
        """Test OllamaClient initialization."""
        client = OllamaClient("http://localhost:11434", timeout=30)
        
        assert client.base_url == "http://localhost:11434"
        assert client.timeout == 30
        assert client.resilience_monitor is not None
        assert client.silent_failure_mode is True
    
    def test_initialization_with_trailing_slash(self):
        """Test URL normalization removes trailing slash."""
        client = OllamaClient("http://localhost:11434/", timeout=30)
        assert client.base_url == "http://localhost:11434"
    
    @pytest.mark.asyncio
    async def test_list_available_models_success(self):
        """Test successful model listing."""
        client = OllamaClient("http://localhost:11434")
        
        mock_response = {
            "models": [
                {"name": "llama3.1"},
                {"name": "codellama"},
                {"name": "mistral"}
            ]
        }
        
        with patch.object(client, '_make_request', new_callable=AsyncMock) as mock_request:
            mock_request.return_value = mock_response
            
            models = await client.list_available_models()
            
            assert models == ["llama3.1", "codellama", "mistral"]
            mock_request.assert_called_once_with("/api/tags")
    
    @pytest.mark.asyncio
    async def test_list_available_models_empty(self):
        """Test model listing with empty response."""
        client = OllamaClient("http://localhost:11434")
        
        with patch.object(client, '_make_request', new_callable=AsyncMock) as mock_request:
            mock_request.return_value = {"models": []}
            
            models = await client.list_available_models()
            
            assert models == []
    
    @pytest.mark.asyncio
    async def test_list_available_models_error(self):
        """Test model listing with API error."""
        client = OllamaClient("http://localhost:11434")
        
        with patch.object(client, '_make_request', new_callable=AsyncMock) as mock_request:
            mock_request.side_effect = OllamaError("API error")
            
            with pytest.raises(OllamaError):
                await client.list_available_models()
    
    @pytest.mark.asyncio
    async def test_validate_model_success(self):
        """Test successful model validation."""
        client = OllamaClient("http://localhost:11434")
        
        with patch.object(client, 'list_available_models', new_callable=AsyncMock) as mock_list:
            mock_list.return_value = ["llama3.1", "codellama"]
            
            result = await client.validate_model("llama3.1")
            assert result is True
            
            result = await client.validate_model("nonexistent")
            assert result is False
    
    @pytest.mark.asyncio
    async def test_validate_model_caching(self):
        """Test model validation caching."""
        client = OllamaClient("http://localhost:11434")
        
        with patch.object(client, 'list_available_models', new_callable=AsyncMock) as mock_list:
            mock_list.return_value = ["llama3.1"]
            
            # First call should hit the API
            result1 = await client.validate_model("llama3.1")
            assert result1 is True
            assert mock_list.call_count == 1
            
            # Second call should use cache
            result2 = await client.validate_model("llama3.1")
            assert result2 is True
            assert mock_list.call_count == 1  # No additional call
    
    @pytest.mark.asyncio
    async def test_validate_startup_model_success(self):
        """Test successful startup model validation."""
        client = OllamaClient("http://localhost:11434")
        
        with patch.object(client, 'is_service_available', new_callable=AsyncMock) as mock_available:
            with patch.object(client, 'validate_model', new_callable=AsyncMock) as mock_validate:
                mock_available.return_value = True
                mock_validate.return_value = True
                
                # Should not raise exception
                await client.validate_startup_model("llama3.1")
    
    @pytest.mark.asyncio
    async def test_validate_startup_model_service_unavailable(self):
        """Test startup model validation when service is unavailable."""
        client = OllamaClient("http://localhost:11434")
        
        with patch.object(client, 'is_service_available', new_callable=AsyncMock) as mock_available:
            mock_available.return_value = False
            
            with pytest.raises(OllamaModelError, match="Ollama service is not available"):
                await client.validate_startup_model("llama3.1")
    
    @pytest.mark.asyncio
    async def test_validate_startup_model_not_found(self):
        """Test startup model validation when model is not found."""
        client = OllamaClient("http://localhost:11434")
        
        with patch.object(client, 'is_service_available', new_callable=AsyncMock) as mock_available:
            with patch.object(client, 'validate_model', new_callable=AsyncMock) as mock_validate:
                with patch.object(client, 'list_available_models', new_callable=AsyncMock) as mock_list:
                    mock_available.return_value = True
                    mock_validate.return_value = False
                    mock_list.return_value = ["llama3.1", "codellama"]
                    
                    with pytest.raises(OllamaModelError, match="Model 'nonexistent' is not available"):
                        await client.validate_startup_model("nonexistent")
    
    @pytest.mark.asyncio
    async def test_is_service_available_success(self):
        """Test service availability check success."""
        client = OllamaClient("http://localhost:11434")
        
        with patch.object(client, 'list_available_models', new_callable=AsyncMock) as mock_list:
            mock_list.return_value = ["llama3.1"]
            
            result = await client.is_service_available()
            assert result is True
    
    @pytest.mark.asyncio
    async def test_is_service_available_failure(self):
        """Test service availability check failure."""
        client = OllamaClient("http://localhost:11434")
        
        with patch.object(client, 'list_available_models', new_callable=AsyncMock) as mock_list:
            mock_list.side_effect = OllamaError("Connection failed")
            
            result = await client.is_service_available()
            assert result is False
    
    @pytest.mark.asyncio
    async def test_validate_model_for_command_success(self):
        """Test model validation for chat command."""
        client = OllamaClient("http://localhost:11434")
        
        with patch.object(client, 'is_service_available', new_callable=AsyncMock) as mock_available:
            with patch.object(client, 'validate_model', new_callable=AsyncMock) as mock_validate:
                mock_available.return_value = True
                mock_validate.return_value = True
                
                is_valid, message = await client.validate_model_for_command("llama3.1")
                assert is_valid is True
                assert message == ""
    
    @pytest.mark.asyncio
    async def test_validate_model_for_command_service_unavailable(self):
        """Test model validation for command when service unavailable."""
        client = OllamaClient("http://localhost:11434")
        
        with patch.object(client, 'is_service_available', new_callable=AsyncMock) as mock_available:
            mock_available.return_value = False
            
            is_valid, message = await client.validate_model_for_command("llama3.1")
            assert is_valid is False
            assert "unavailable" in message.lower()
    
    @pytest.mark.asyncio
    async def test_validate_model_for_command_model_not_found(self):
        """Test model validation for command when model not found."""
        client = OllamaClient("http://localhost:11434")
        
        with patch.object(client, 'is_service_available', new_callable=AsyncMock) as mock_available:
            with patch.object(client, 'validate_model', new_callable=AsyncMock) as mock_validate:
                with patch.object(client, 'list_available_models', new_callable=AsyncMock) as mock_list:
                    mock_available.return_value = True
                    mock_validate.return_value = False
                    mock_list.return_value = ["llama3.1", "codellama"]
                    
                    is_valid, message = await client.validate_model_for_command("nonexistent")
                    assert is_valid is False
                    assert "not found" in message.lower()
                    assert "llama3.1" in message
    
    def test_format_context_for_spontaneous(self):
        """Test context formatting for spontaneous messages."""
        client = OllamaClient("http://localhost:11434")
        
        messages = [
            create_test_message("msg1", content="Hello everyone!"),
            create_test_message("msg2", content="How's it going?"),
            create_test_message("msg3", content="Great stream today!")
        ]
        
        context = client.format_context_for_spontaneous(messages)
        
        assert "Recent chat messages:" in context
        assert "[TestUser]: Hello everyone!" in context
        assert "[TestUser]: How's it going?" in context
        assert "[TestUser]: Great stream today!" in context
        assert "Generate a natural chat message" in context
    
    def test_format_context_for_spontaneous_empty(self):
        """Test context formatting with no messages."""
        client = OllamaClient("http://localhost:11434")
        
        context = client.format_context_for_spontaneous([])
        
        assert "Recent chat messages:" in context
        assert "(No recent messages)" in context
        assert "Generate a natural chat message" in context
    
    def test_format_context_for_response(self):
        """Test context formatting for response messages."""
        client = OllamaClient("http://localhost:11434")
        
        messages = [
            create_test_message("msg1", content="Hello everyone!"),
            create_test_message("msg2", content="How's it going?")
        ]
        
        context = client.format_context_for_response(messages, "What do you think?", "TestUser")
        
        assert "Recent chat messages:" in context
        assert "[TestUser]: Hello everyone!" in context
        assert "[TestUser]: How's it going?" in context
        assert 'Generate a response to TestUser\'s message: "What do you think?"' in context
    
    def test_format_context_for_response_empty(self):
        """Test response context formatting with no messages."""
        client = OllamaClient("http://localhost:11434")
        
        context = client.format_context_for_response([], "Hello bot!", "TestUser")
        
        assert "Recent chat messages:" in context
        assert "(No recent messages)" in context
        assert 'Generate a response to TestUser\'s message: "Hello bot!"' in context
    
    def test_validate_response_success(self):
        """Test successful response validation."""
        client = OllamaClient("http://localhost:11434")
        
        response = "This is a valid response!"
        validated = client.validate_response(response)
        
        assert validated == "This is a valid response!"
    
    def test_validate_response_empty(self):
        """Test validation of empty response."""
        client = OllamaClient("http://localhost:11434")
        
        with pytest.raises(OllamaError, match="Empty response"):
            client.validate_response("")
        
        with pytest.raises(OllamaError, match="Empty response"):
            client.validate_response("   ")
    
    def test_validate_response_markdown_removal(self):
        """Test markdown formatting removal."""
        client = OllamaClient("http://localhost:11434")
        
        response = "This is **bold** and *italic* and `code`"
        validated = client.validate_response(response)
        
        assert validated == "This is bold and italic and code"
    
    def test_validate_response_multiline_first_line(self):
        """Test that only first non-empty line is used."""
        client = OllamaClient("http://localhost:11434")
        
        response = "First line\nSecond line\nThird line"
        validated = client.validate_response(response)
        
        assert validated == "First line"
    
    def test_validate_response_length_truncation(self):
        """Test response length truncation."""
        client = OllamaClient("http://localhost:11434")
        
        # Create a response longer than 500 characters
        long_response = "This is a very long response " * 20  # Much longer than 500 chars
        validated = client.validate_response(long_response)
        
        assert len(validated) <= 500
        assert validated.endswith("...")
    
    def test_validate_response_special_character_removal(self):
        """Test removal of special characters."""
        client = OllamaClient("http://localhost:11434")
        
        response = "Hello! 😀 This has émojis and spëcial chars"
        validated = client.validate_response(response)
        
        # Should remove emoji and special unicode
        assert "😀" not in validated
        assert "émojis" not in validated or "emojis" in validated
    
    @pytest.mark.asyncio
    async def test_generate_message_success(self):
        """Test successful message generation."""
        client = OllamaClient("http://localhost:11434")
        
        mock_response = {
            "response": "This is a generated message!"
        }
        
        with patch.object(client, '_make_request', new_callable=AsyncMock) as mock_request:
            mock_request.return_value = mock_response
            
            result = await client._generate_message("llama3.1", "System prompt", "Context")
            
            assert result == "This is a generated message!"
            mock_request.assert_called_once()
            
            # Check request data
            call_args = mock_request.call_args
            assert call_args[0][0] == "/api/generate"
            request_data = call_args[1]["data"]
            assert request_data["model"] == "llama3.1"
            assert "System prompt" in request_data["prompt"]
            assert "Context" in request_data["prompt"]
    
    @pytest.mark.asyncio
    async def test_generate_message_invalid_response(self):
        """Test generation with invalid response format."""
        client = OllamaClient("http://localhost:11434")
        
        with patch.object(client, '_make_request', new_callable=AsyncMock) as mock_request:
            mock_request.return_value = {"error": "No response field"}
            
            with pytest.raises(OllamaError, match="Invalid response format"):
                await client._generate_message("llama3.1", "System prompt", "Context")
    
    @pytest.mark.asyncio
    async def test_generate_spontaneous_message_success(self):
        """Test successful spontaneous message generation."""
        client = OllamaClient("http://localhost:11434")
        
        messages = [create_test_message("msg1", content="Hello!")]
        
        with patch.object(client, 'generate_with_fallback', new_callable=AsyncMock) as mock_fallback:
            mock_fallback.return_value = "Generated message"
            
            result = await client.generate_spontaneous_message("llama3.1", messages)
            
            assert result == "Generated message"
            mock_fallback.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_generate_response_message_success(self):
        """Test successful response message generation."""
        client = OllamaClient("http://localhost:11434")
        
        messages = [create_test_message("msg1", content="Hello!")]
        
        with patch.object(client, 'generate_with_fallback', new_callable=AsyncMock) as mock_fallback:
            mock_fallback.return_value = "Response message"
            
            result = await client.generate_response_message("llama3.1", messages, "How are you?", "TestUser")
            
            assert result == "Response message"
            mock_fallback.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_generate_with_fallback_skip_when_unavailable(self):
        """Test that generation is skipped when service is unavailable."""
        client = OllamaClient("http://localhost:11434")
        client.resilience_monitor.state = OllamaServiceState.UNAVAILABLE
        
        async def mock_operation():
            return "Should not be called"
        
        result = await client.generate_with_fallback(mock_operation, "test")
        assert result is None
    
    @pytest.mark.asyncio
    async def test_generate_with_fallback_timeout_handling(self):
        """Test timeout handling in generation fallback."""
        client = OllamaClient("http://localhost:11434")
        
        async def mock_operation():
            raise asyncio.TimeoutError("Request timed out")
        
        result = await client.generate_with_fallback(mock_operation, "test")
        assert result is None  # Should return None in silent mode
        assert client.resilience_monitor.consecutive_failures > 0
    
    @pytest.mark.asyncio
    async def test_generate_with_fallback_success_resets_failures(self):
        """Test that successful generation resets failure count."""
        client = OllamaClient("http://localhost:11434")
        client.resilience_monitor.consecutive_failures = 2
        
        async def mock_operation():
            return "Success!"
        
        result = await client.generate_with_fallback(mock_operation, "test")
        assert result == "Success!"
        assert client.resilience_monitor.consecutive_failures == 0
    
    @pytest.mark.asyncio
    async def test_make_request_timeout(self):
        """Test request timeout handling."""
        client = OllamaClient("http://localhost:11434", timeout=1)
        
        with patch('aiohttp.ClientSession.post') as mock_post:
            mock_post.side_effect = asyncio.TimeoutError()
            
            with pytest.raises(OllamaTimeoutError):
                await client._make_request("/api/generate", {"test": "data"})
    
    @pytest.mark.asyncio
    async def test_make_request_client_error(self):
        """Test client error handling."""
        client = OllamaClient("http://localhost:11434")
        
        with patch('aiohttp.ClientSession.post') as mock_post:
            mock_post.side_effect = aiohttp.ClientError("Connection failed")
            
            with pytest.raises(OllamaError, match="Client error"):
                await client._make_request("/api/generate", {"test": "data"})
    
    @pytest.mark.asyncio
    async def test_make_request_http_error(self):
        """Test HTTP error response handling."""
        client = OllamaClient("http://localhost:11434")
        
        mock_response = Mock()
        mock_response.status = 500
        mock_response.text = AsyncMock(return_value="Internal server error")
        
        with patch('aiohttp.ClientSession.post') as mock_post:
            mock_post.return_value.__aenter__.return_value = mock_response
            
            with pytest.raises(OllamaError, match="API request failed with status 500"):
                await client._make_request("/api/generate", {"test": "data"})
    
    def test_get_service_status(self):
        """Test getting service status information."""
        client = OllamaClient("http://localhost:11434", timeout=30)
        
        status = client.get_service_status()
        
        assert isinstance(status, dict)
        assert status['base_url'] == "http://localhost:11434"
        assert status['timeout'] == 30
        assert status['silent_failure_mode'] is True
        assert 'state' in status
        assert 'consecutive_failures' in status
    
    @pytest.mark.asyncio
    async def test_close_session(self):
        """Test closing HTTP session."""
        client = OllamaClient("http://localhost:11434")
        
        # Create a session
        await client._get_session()
        assert client._session is not None
        
        # Close it
        await client.close()
        
        # Session should be closed
        if client._session:
            assert client._session.closed


class TestOllamaResilienceMonitor:
    """Test cases for OllamaResilienceMonitor class."""
    
    def test_initialization(self):
        """Test resilience monitor initialization."""
        monitor = OllamaResilienceMonitor(max_failures=5, recovery_timeout=600)
        
        assert monitor.max_failures == 5
        assert monitor.recovery_timeout == 600
        assert monitor.state == OllamaServiceState.HEALTHY
        assert monitor.consecutive_failures == 0
    
    def test_record_success(self):
        """Test recording successful operations."""
        monitor = OllamaResilienceMonitor()
        monitor.consecutive_failures = 3
        monitor.state = OllamaServiceState.DEGRADED
        
        monitor.record_success()
        
        assert monitor.state == OllamaServiceState.HEALTHY
        assert monitor.consecutive_failures == 0
        assert monitor.unavailable_since is None
    
    def test_record_failure_progression(self):
        """Test failure recording and state progression."""
        monitor = OllamaResilienceMonitor(max_failures=3)
        
        # First failure - should stay healthy
        monitor.record_failure(Exception("Error 1"), "test")
        assert monitor.state == OllamaServiceState.HEALTHY
        assert monitor.consecutive_failures == 1
        
        # Second failure - should become degraded
        monitor.record_failure(Exception("Error 2"), "test")
        assert monitor.state == OllamaServiceState.DEGRADED
        assert monitor.consecutive_failures == 2
        
        # Third failure - should become unavailable
        monitor.record_failure(Exception("Error 3"), "test")
        assert monitor.state == OllamaServiceState.UNAVAILABLE
        assert monitor.consecutive_failures == 3
        assert monitor.unavailable_since is not None
    
    def test_is_available_healthy(self):
        """Test availability check when healthy."""
        monitor = OllamaResilienceMonitor()
        assert monitor.is_available() is True
    
    def test_is_available_degraded(self):
        """Test availability check when degraded."""
        monitor = OllamaResilienceMonitor()
        monitor.state = OllamaServiceState.DEGRADED
        assert monitor.is_available() is True
    
    def test_is_available_unavailable(self):
        """Test availability check when unavailable."""
        monitor = OllamaResilienceMonitor()
        monitor.state = OllamaServiceState.UNAVAILABLE
        monitor.unavailable_since = datetime.now()
        assert monitor.is_available() is False
    
    def test_is_available_recovery_timeout(self):
        """Test availability check after recovery timeout."""
        monitor = OllamaResilienceMonitor(recovery_timeout=1)
        monitor.state = OllamaServiceState.UNAVAILABLE
        monitor.unavailable_since = datetime.now() - timedelta(seconds=2)
        
        # Should allow recovery attempt
        assert monitor.is_available() is True
        assert monitor.state == OllamaServiceState.RECOVERING
    
    def test_model_validation_caching(self):
        """Test model validation caching."""
        monitor = OllamaResilienceMonitor()
        
        # Initially no cache
        assert monitor.is_model_validated("llama3.1") is None
        
        # Cache a result
        monitor.cache_model_validation("llama3.1", True)
        assert monitor.is_model_validated("llama3.1") is True
        
        # Cache another result
        monitor.cache_model_validation("nonexistent", False)
        assert monitor.is_model_validated("nonexistent") is False
    
    def test_model_validation_cache_expiry(self):
        """Test model validation cache expiry."""
        monitor = OllamaResilienceMonitor()
        monitor.model_cache_ttl = 0.1  # Very short TTL for testing
        
        # Cache a result
        monitor.cache_model_validation("llama3.1", True)
        assert monitor.is_model_validated("llama3.1") is True
        
        # Wait for expiry
        import time
        time.sleep(0.2)
        
        # Should be expired
        assert monitor.is_model_validated("llama3.1") is None
    
    def test_get_status(self):
        """Test getting status information."""
        monitor = OllamaResilienceMonitor()
        monitor.record_failure(Exception("Test error"), "test")
        
        status = monitor.get_status()
        
        assert isinstance(status, dict)
        assert status['state'] == 'healthy'  # Still healthy after 1 failure
        assert status['consecutive_failures'] == 1
        assert 'last_success_time' in status
        assert 'time_since_last_success' in status
        assert 'last_failure_time' in status
        assert 'time_since_last_failure' in status