"""
Unit tests for ConfigurationManager.

Tests chat command processing, configuration validation, and user permissions.
"""

import pytest
from unittest.mock import Mock, AsyncMock, patch
from datetime import datetime, timedelta

from chatbot.config.commands import ConfigurationManager
from chatbot.database.operations import ChannelConfigManager
from chatbot.ollama.client import OllamaClient
from tests.conftest import create_test_config


class TestConfigurationManager:
    """Test cases for ConfigurationManager class."""
    
    def test_initialization(self, channel_config_manager, mock_ollama_client):
        """Test ConfigurationManager initialization."""
        config_manager = ConfigurationManager(channel_config_manager, mock_ollama_client)
        
        assert config_manager.channel_config == channel_config_manager
        assert config_manager.ollama_client == mock_ollama_client
        assert len(config_manager.valid_settings) > 0
        assert 'threshold' in config_manager.valid_settings
        assert 'spontaneous' in config_manager.valid_settings
        assert 'response' in config_manager.valid_settings
        assert 'context' in config_manager.valid_settings
        assert 'model' in config_manager.valid_settings
    
    @pytest.mark.asyncio
    async def test_process_chat_command_help(self, configuration_manager, moderator_badges):
        """Test processing help command."""
        response = await configuration_manager.process_chat_command(
            "testchannel", "TestMod", "!clank", moderator_badges
        )
        
        assert "Available !clank commands:" in response
        assert "threshold" in response
        assert "spontaneous" in response
        assert "response" in response
        assert "context" in response
        assert "model" in response
        assert "status" in response
    
    @pytest.mark.asyncio
    async def test_process_chat_command_unauthorized(self, configuration_manager, regular_user_badges):
        """Test processing command without authorization."""
        response = await configuration_manager.process_chat_command(
            "testchannel", "RegularUser", "!clank threshold", regular_user_badges
        )
        
        assert "need to be a moderator or broadcaster" in response
        assert "RegularUser" in response
    
    @pytest.mark.asyncio
    async def test_process_chat_command_show_setting(self, configuration_manager, moderator_badges):
        """Test showing current setting value."""
        # Mock the channel config
        with patch.object(configuration_manager.channel_config, 'get_config', new_callable=AsyncMock) as mock_get:
            mock_config = create_test_config(message_threshold=45)
            mock_get.return_value = mock_config
            
            response = await configuration_manager.process_chat_command(
                "testchannel", "TestMod", "!clank threshold", moderator_badges
            )
            
            assert "threshold: 45" in response
            assert "Message count threshold" in response
    
    @pytest.mark.asyncio
    async def test_process_chat_command_set_setting_success(self, configuration_manager, moderator_badges):
        """Test successfully setting a configuration value."""
        with patch.object(configuration_manager.channel_config, 'get_config', new_callable=AsyncMock) as mock_get:
            with patch.object(configuration_manager.channel_config, 'update_config', new_callable=AsyncMock) as mock_update:
                mock_config = create_test_config()
                mock_get.return_value = mock_config
                mock_update.return_value = True
                
                response = await configuration_manager.process_chat_command(
                    "testchannel", "TestMod", "!clank threshold 50", moderator_badges
                )
                
                assert "threshold updated to: 50" in response
                mock_update.assert_called_once_with("testchannel", "message_threshold", 50)
    
    @pytest.mark.asyncio
    async def test_process_chat_command_set_setting_invalid_value(self, configuration_manager, moderator_badges):
        """Test setting invalid configuration value."""
        response = await configuration_manager.process_chat_command(
            "testchannel", "TestMod", "!clank threshold -5", moderator_badges
        )
        
        assert "must be at least" in response
    
    @pytest.mark.asyncio
    async def test_process_chat_command_set_setting_database_error(self, configuration_manager, moderator_badges):
        """Test setting configuration when database update fails."""
        with patch.object(configuration_manager.channel_config, 'get_config', new_callable=AsyncMock) as mock_get:
            with patch.object(configuration_manager.channel_config, 'update_config', new_callable=AsyncMock) as mock_update:
                mock_config = create_test_config()
                mock_get.return_value = mock_config
                mock_update.return_value = False  # Simulate database failure
                
                response = await configuration_manager.process_chat_command(
                    "testchannel", "TestMod", "!clank threshold 50", moderator_badges
                )
                
                assert "Failed to update threshold" in response
    
    @pytest.mark.asyncio
    async def test_process_chat_command_model_setting_success(self, configuration_manager, moderator_badges):
        """Test successfully setting model configuration."""
        with patch.object(configuration_manager.channel_config, 'get_config', new_callable=AsyncMock) as mock_get:
            with patch.object(configuration_manager.channel_config, 'update_config', new_callable=AsyncMock) as mock_update:
                mock_config = create_test_config()
                mock_get.return_value = mock_config
                mock_update.return_value = True
                
                # Mock successful model validation
                configuration_manager.ollama_client.validate_model.return_value = True
                
                response = await configuration_manager.process_chat_command(
                    "testchannel", "TestMod", "!clank model llama3.1", moderator_badges
                )
                
                assert "model updated to: llama3.1" in response
                mock_update.assert_called_once_with("testchannel", "ollama_model", "llama3.1")
    
    @pytest.mark.asyncio
    async def test_process_chat_command_model_setting_invalid(self, configuration_manager, moderator_badges):
        """Test setting invalid model configuration."""
        # Mock model validation failure
        configuration_manager.ollama_client.validate_model.return_value = False
        configuration_manager.ollama_client.list_available_models.return_value = ["llama3.1", "codellama"]
        
        response = await configuration_manager.process_chat_command(
            "testchannel", "TestMod", "!clank model nonexistent", moderator_badges
        )
        
        assert "not found" in response
        assert "llama3.1" in response  # Should show available models
    
    @pytest.mark.asyncio
    async def test_process_chat_command_model_default(self, configuration_manager, moderator_badges):
        """Test setting model to default."""
        with patch.object(configuration_manager.channel_config, 'get_config', new_callable=AsyncMock) as mock_get:
            with patch.object(configuration_manager.channel_config, 'update_config', new_callable=AsyncMock) as mock_update:
                mock_config = create_test_config()
                mock_get.return_value = mock_config
                mock_update.return_value = True
                
                response = await configuration_manager.process_chat_command(
                    "testchannel", "TestMod", "!clank model default", moderator_badges
                )
                
                assert "model updated to: None" in response
                mock_update.assert_called_once_with("testchannel", "ollama_model", None)
    
    @pytest.mark.asyncio
    async def test_process_chat_command_status(self, configuration_manager, moderator_badges):
        """Test status command."""
        with patch.object(configuration_manager.channel_config, 'get_config', new_callable=AsyncMock) as mock_get:
            mock_config = create_test_config(message_count=15, message_threshold=30)
            mock_get.return_value = mock_config
            
            # Mock Ollama status
            configuration_manager.ollama_client.list_available_models.return_value = ["llama3.1", "codellama"]
            
            response = await configuration_manager.process_chat_command(
                "testchannel", "TestMod", "!clank status", moderator_badges
            )
            
            assert "Status -" in response
            assert "Ollama:" in response
            assert "Model:" in response
            assert "Messages: 15/30" in response
            assert "Cooldowns:" in response
    
    @pytest.mark.asyncio
    async def test_process_chat_command_status_ollama_error(self, configuration_manager, moderator_badges):
        """Test status command when Ollama is unavailable."""
        with patch.object(configuration_manager.channel_config, 'get_config', new_callable=AsyncMock) as mock_get:
            mock_config = create_test_config()
            mock_get.return_value = mock_config
            
            # Mock Ollama error
            configuration_manager.ollama_client.list_available_models.side_effect = Exception("Connection failed")
            
            response = await configuration_manager.process_chat_command(
                "testchannel", "TestMod", "!clank status", moderator_badges
            )
            
            assert "Status -" in response
            assert "Disconnected" in response
    
    @pytest.mark.asyncio
    async def test_process_chat_command_unknown_setting(self, configuration_manager, moderator_badges):
        """Test processing command with unknown setting."""
        response = await configuration_manager.process_chat_command(
            "testchannel", "TestMod", "!clank unknown", moderator_badges
        )
        
        assert "Available !clank commands:" in response
    
    @pytest.mark.asyncio
    async def test_process_chat_command_too_many_args(self, configuration_manager, moderator_badges):
        """Test processing command with too many arguments."""
        response = await configuration_manager.process_chat_command(
            "testchannel", "TestMod", "!clank threshold 50 extra args", moderator_badges
        )
        
        assert "Usage: !clank threshold [value]" in response
    
    @pytest.mark.asyncio
    async def test_process_chat_command_exception_handling(self, configuration_manager, moderator_badges):
        """Test exception handling in command processing."""
        with patch.object(configuration_manager, 'check_user_permissions', side_effect=Exception("Test error")):
            response = await configuration_manager.process_chat_command(
                "testchannel", "TestMod", "!clank threshold", moderator_badges
            )
            
            assert "error occurred" in response
    
    def test_check_user_permissions_moderator(self, configuration_manager):
        """Test user permission checking for moderator."""
        result = configuration_manager.is_channel_owner_or_mod({"moderator": "1"})
        assert result is True
    
    def test_check_user_permissions_broadcaster(self, configuration_manager):
        """Test user permission checking for broadcaster."""
        result = configuration_manager.is_channel_owner_or_mod({"broadcaster": "1"})
        assert result is True
    
    def test_check_user_permissions_regular_user(self, configuration_manager):
        """Test user permission checking for regular user."""
        result = configuration_manager.is_channel_owner_or_mod({"subscriber": "1"})
        assert result is False
    
    def test_check_user_permissions_no_badges(self, configuration_manager):
        """Test user permission checking with no badges."""
        result = configuration_manager.is_channel_owner_or_mod({})
        assert result is False
    
    @pytest.mark.asyncio
    async def test_validate_setting_value_threshold_valid(self, configuration_manager):
        """Test validating valid threshold setting."""
        is_valid, message, value = await configuration_manager.validate_setting_value("threshold", "50")
        
        assert is_valid is True
        assert message == ""
        assert value == 50
    
    @pytest.mark.asyncio
    async def test_validate_setting_value_threshold_invalid_range(self, configuration_manager):
        """Test validating threshold setting out of range."""
        # Too low
        is_valid, message, value = await configuration_manager.validate_setting_value("threshold", "0")
        assert is_valid is False
        assert "must be at least" in message
        
        # Too high
        is_valid, message, value = await configuration_manager.validate_setting_value("threshold", "2000")
        assert is_valid is False
        assert "must be at most" in message
    
    @pytest.mark.asyncio
    async def test_validate_setting_value_threshold_invalid_type(self, configuration_manager):
        """Test validating threshold setting with invalid type."""
        is_valid, message, value = await configuration_manager.validate_setting_value("threshold", "not_a_number")
        
        assert is_valid is False
        assert "Invalid value" in message
    
    @pytest.mark.asyncio
    async def test_validate_setting_value_model_valid(self, configuration_manager):
        """Test validating valid model setting."""
        is_valid, message, value = await configuration_manager.validate_setting_value("model", "llama3.1")
        
        assert is_valid is True
        assert message == ""
        assert value == "llama3.1"
    
    @pytest.mark.asyncio
    async def test_validate_setting_value_model_default(self, configuration_manager):
        """Test validating model setting to default."""
        for default_value in ["default", "global", "none", ""]:
            is_valid, message, value = await configuration_manager.validate_setting_value("model", default_value)
            
            assert is_valid is True
            assert message == ""
            assert value is None
    
    @pytest.mark.asyncio
    async def test_validate_setting_value_model_invalid_chars(self, configuration_manager):
        """Test validating model setting with invalid characters."""
        is_valid, message, value = await configuration_manager.validate_setting_value("model", "invalid/model*name")
        
        assert is_valid is False
        assert "invalid characters" in message
    
    @pytest.mark.asyncio
    async def test_validate_setting_value_unknown_setting(self, configuration_manager):
        """Test validating unknown setting."""
        is_valid, message, value = await configuration_manager.validate_setting_value("unknown", "value")
        
        assert is_valid is False
        assert "Unknown setting" in message
    
    @pytest.mark.asyncio
    async def test_validate_model_change_success(self, configuration_manager):
        """Test successful model validation."""
        configuration_manager.ollama_client.validate_model.return_value = True
        
        is_valid, message = await configuration_manager.validate_model_change("llama3.1")
        
        assert is_valid is True
        assert "available" in message
    
    @pytest.mark.asyncio
    async def test_validate_model_change_not_found(self, configuration_manager):
        """Test model validation when model not found."""
        configuration_manager.ollama_client.validate_model.return_value = False
        configuration_manager.ollama_client.list_available_models.return_value = ["llama3.1", "codellama"]
        
        is_valid, message = await configuration_manager.validate_model_change("nonexistent")
        
        assert is_valid is False
        assert "not found" in message
        assert "llama3.1" in message
    
    @pytest.mark.asyncio
    async def test_validate_model_change_default(self, configuration_manager):
        """Test model validation for default model."""
        is_valid, message = await configuration_manager.validate_model_change(None)
        
        assert is_valid is True
        assert "global default" in message
    
    @pytest.mark.asyncio
    async def test_validate_model_change_validation_error(self, configuration_manager):
        """Test model validation when validation fails."""
        configuration_manager.ollama_client.validate_model.side_effect = Exception("Connection error")
        
        is_valid, message = await configuration_manager.validate_model_change("llama3.1")
        
        # Should allow the change but warn about validation unavailability
        assert is_valid is True
        assert "validation unavailable" in message
    
    @pytest.mark.asyncio
    async def test_get_ollama_status_success(self, configuration_manager):
        """Test getting Ollama status successfully."""
        mock_config = create_test_config(ollama_model="llama3.1")
        configuration_manager.ollama_client.list_available_models.return_value = ["llama3.1", "codellama"]
        
        status, model_info, response_time = await configuration_manager._get_ollama_status(mock_config)
        
        assert status == "Connected"
        assert "llama3.1" in model_info
        assert "(2 available)" in model_info
        assert isinstance(response_time, int)
        assert response_time > 0
    
    @pytest.mark.asyncio
    async def test_get_ollama_status_model_not_found(self, configuration_manager):
        """Test getting Ollama status when configured model not found."""
        mock_config = create_test_config(ollama_model="nonexistent")
        configuration_manager.ollama_client.list_available_models.return_value = ["llama3.1", "codellama"]
        
        status, model_info, response_time = await configuration_manager._get_ollama_status(mock_config)
        
        assert status == "Connected (model issue)"
        assert "nonexistent (NOT FOUND)" in model_info
    
    @pytest.mark.asyncio
    async def test_get_ollama_status_connection_error(self, configuration_manager):
        """Test getting Ollama status when connection fails."""
        mock_config = create_test_config()
        configuration_manager.ollama_client.list_available_models.side_effect = Exception("Connection failed")
        
        status, model_info, response_time = await configuration_manager._get_ollama_status(mock_config)
        
        assert status == "Disconnected"
        assert "Error:" in model_info
        assert response_time is None
    
    @pytest.mark.asyncio
    async def test_get_cooldown_status(self, configuration_manager):
        """Test getting cooldown status information."""
        # Test with no previous spontaneous message
        mock_config = create_test_config(
            spontaneous_cooldown=300,
            response_cooldown=60,
            last_spontaneous_message=None
        )
        
        cooldown_info = await configuration_manager._get_cooldown_status(mock_config)
        
        assert "Spont: Ready" in cooldown_info
        assert "Resp: 60s" in cooldown_info
    
    @pytest.mark.asyncio
    async def test_get_cooldown_status_with_active_cooldown(self, configuration_manager):
        """Test getting cooldown status with active cooldown."""
        # Set last message to 2 minutes ago with 5 minute cooldown
        last_message_time = datetime.now() - timedelta(minutes=2)
        mock_config = create_test_config(
            spontaneous_cooldown=300,  # 5 minutes
            response_cooldown=60,
            last_spontaneous_message=last_message_time
        )
        
        cooldown_info = await configuration_manager._get_cooldown_status(mock_config)
        
        # Should show remaining time (approximately 3 minutes = 180 seconds)
        assert "Spont:" in cooldown_info
        assert "s" in cooldown_info  # Should show seconds remaining
        assert "Resp: 60s" in cooldown_info
    
    @pytest.mark.asyncio
    async def test_get_cooldown_status_cooldown_expired(self, configuration_manager):
        """Test getting cooldown status when cooldown has expired."""
        # Set last message to 10 minutes ago with 5 minute cooldown
        last_message_time = datetime.now() - timedelta(minutes=10)
        mock_config = create_test_config(
            spontaneous_cooldown=300,  # 5 minutes
            response_cooldown=60,
            last_spontaneous_message=last_message_time
        )
        
        cooldown_info = await configuration_manager._get_cooldown_status(mock_config)
        
        assert "Spont: Ready" in cooldown_info
        assert "Resp: 60s" in cooldown_info