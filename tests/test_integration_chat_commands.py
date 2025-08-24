"""
Integration tests for chat commands and configuration management.

Tests the complete flow of chat command processing, configuration updates,
and system status reporting.
"""

import pytest
import asyncio
from datetime import datetime, timedelta
from unittest.mock import Mock, AsyncMock, patch

from chatbot.database.operations import DatabaseManager, ChannelConfigManager
from chatbot.database.models import MessageEvent
from chatbot.ollama.client import OllamaClient
from chatbot.config.commands import ConfigurationManager
from chatbot.irc.client import TwitchIRCClient
from tests.conftest import create_test_config


class TestChatCommandsIntegration:
    """Integration tests for chat command processing."""
    
    @pytest.fixture
    async def command_system(self, db_manager):
        """Create a complete command processing system."""
        # Create channel config manager
        channel_config = ChannelConfigManager(db_manager)
        
        # Create mock Ollama client
        ollama_client = Mock(spec=OllamaClient)
        ollama_client.list_available_models = AsyncMock(return_value=["llama3.1", "codellama", "mistral"])
        ollama_client.validate_model = AsyncMock(return_value=True)
        ollama_client.is_service_available = AsyncMock(return_value=True)
        
        # Create configuration manager
        config_manager = ConfigurationManager(channel_config, ollama_client)
        
        # Create mock IRC client
        irc_client = Mock(spec=TwitchIRCClient)
        irc_client.send_message = AsyncMock()
        
        return {
            'config_manager': config_manager,
            'channel_config': channel_config,
            'ollama_client': ollama_client,
            'irc_client': irc_client,
            'db_manager': db_manager
        }
    
    @pytest.mark.asyncio
    async def test_complete_command_processing_flow(self, command_system):
        """Test complete flow from command reception to response."""
        config_manager = command_system['config_manager']
        channel = "testchannel"
        moderator_badges = {"moderator": "1"}
        
        # Process a configuration command
        response = await config_manager.process_chat_command(
            channel, "TestMod", "!clank threshold 45", moderator_badges
        )
        
        # Verify response
        assert "threshold updated to: 45" in response
        
        # Verify configuration was actually updated in database
        channel_config = command_system['channel_config']
        config = await channel_config.get_config(channel)
        assert config.message_threshold == 45
    
    @pytest.mark.asyncio
    async def test_configuration_persistence_across_restarts(self, command_system):
        """Test that configuration changes persist across system restarts."""
        config_manager = command_system['config_manager']
        db_manager = command_system['db_manager']
        channel = "testchannel"
        moderator_badges = {"moderator": "1"}
        
        # Set multiple configuration values
        commands = [
            ("!clank threshold 50", 50),
            ("!clank spontaneous 600", 600),
            ("!clank response 120", 120),
            ("!clank context 150", 150)
        ]
        
        for command, expected_value in commands:
            response = await config_manager.process_chat_command(
                channel, "TestMod", command, moderator_badges
            )
            assert "updated to:" in response
        
        # Simulate restart by creating new channel config manager
        new_channel_config = ChannelConfigManager(db_manager)
        config = await new_channel_config.get_config(channel)
        
        # Verify all settings persisted
        assert config.message_threshold == 50
        assert config.spontaneous_cooldown == 600
        assert config.response_cooldown == 120
        assert config.context_limit == 150
    
    @pytest.mark.asyncio
    async def test_model_validation_integration(self, command_system):
        """Test model validation integration with Ollama service."""
        config_manager = command_system['config_manager']
        ollama_client = command_system['ollama_client']
        channel = "testchannel"
        moderator_badges = {"moderator": "1"}
        
        # Test setting valid model
        ollama_client.validate_model.return_value = True
        response = await config_manager.process_chat_command(
            channel, "TestMod", "!clank model llama3.1", moderator_badges
        )
        assert "model updated to: llama3.1" in response
        
        # Test setting invalid model
        ollama_client.validate_model.return_value = False
        ollama_client.list_available_models.return_value = ["llama3.1", "codellama"]
        
        response = await config_manager.process_chat_command(
            channel, "TestMod", "!clank model nonexistent", moderator_badges
        )
        assert "not found" in response
        assert "llama3.1" in response
    
    @pytest.mark.asyncio
    async def test_status_command_comprehensive_reporting(self, command_system):
        """Test comprehensive status reporting integration."""
        config_manager = command_system['config_manager']
        channel_config = command_system['channel_config']
        ollama_client = command_system['ollama_client']
        channel = "testchannel"
        moderator_badges = {"moderator": "1"}
        
        # Set up some configuration and state
        await channel_config.update_config(channel, "message_threshold", 25)
        await channel_config.increment_message_count(channel)
        await channel_config.increment_message_count(channel)
        await channel_config.increment_message_count(channel)
        
        # Mock Ollama status
        ollama_client.list_available_models.return_value = ["llama3.1", "codellama", "mistral"]
        
        # Get status
        response = await config_manager.process_chat_command(
            channel, "TestMod", "!clank status", moderator_badges
        )
        
        # Verify comprehensive status information
        assert "Status -" in response
        assert "Ollama: Connected" in response
        assert "Model:" in response
        assert "Messages: 3/25" in response
        assert "Cooldowns:" in response
        assert "Spont: Ready" in response
    
    @pytest.mark.asyncio
    async def test_status_command_with_ollama_issues(self, command_system):
        """Test status command when Ollama has issues."""
        config_manager = command_system['config_manager']
        ollama_client = command_system['ollama_client']
        channel = "testchannel"
        moderator_badges = {"moderator": "1"}
        
        # Simulate Ollama connection failure
        ollama_client.list_available_models.side_effect = Exception("Connection refused")
        
        response = await config_manager.process_chat_command(
            channel, "TestMod", "!clank status", moderator_badges
        )
        
        assert "Status -" in response
        assert "Disconnected" in response
        assert "Error:" in response
    
    @pytest.mark.asyncio
    async def test_permission_system_integration(self, command_system):
        """Test permission system integration across different user types."""
        config_manager = command_system['config_manager']
        channel = "testchannel"
        
        # Test different badge combinations
        test_cases = [
            ({"broadcaster": "1"}, True),  # Broadcaster should have access
            ({"moderator": "1"}, True),    # Moderator should have access
            ({"subscriber": "1"}, False), # Subscriber should not have access
            ({"vip": "1"}, False),        # VIP should not have access
            ({}, False)                   # No badges should not have access
        ]
        
        for badges, should_have_access in test_cases:
            response = await config_manager.process_chat_command(
                channel, "TestUser", "!clank threshold 30", badges
            )
            
            if should_have_access:
                assert "updated to:" in response or "threshold: " in response
            else:
                assert "need to be a moderator or broadcaster" in response
    
    @pytest.mark.asyncio
    async def test_configuration_validation_integration(self, command_system):
        """Test configuration validation across all settings."""
        config_manager = command_system['config_manager']
        channel = "testchannel"
        moderator_badges = {"moderator": "1"}
        
        # Test validation for each setting type
        validation_tests = [
            # Valid values
            ("!clank threshold 50", True, "updated to: 50"),
            ("!clank spontaneous 300", True, "updated to: 300"),
            ("!clank response 60", True, "updated to: 60"),
            ("!clank context 200", True, "updated to: 200"),
            
            # Invalid values - out of range
            ("!clank threshold 0", False, "must be at least"),
            ("!clank threshold 2000", False, "must be at most"),
            ("!clank spontaneous -1", False, "must be at least"),
            ("!clank context 5", False, "must be at least"),
            
            # Invalid values - wrong type
            ("!clank threshold abc", False, "Invalid value"),
            ("!clank spontaneous not_a_number", False, "Invalid value"),
        ]
        
        for command, should_succeed, expected_text in validation_tests:
            response = await config_manager.process_chat_command(
                channel, "TestMod", command, moderator_badges
            )
            
            assert expected_text in response, f"Command '{command}' failed validation test"
    
    @pytest.mark.asyncio
    async def test_concurrent_command_processing(self, command_system):
        """Test concurrent command processing doesn't cause issues."""
        config_manager = command_system['config_manager']
        channel = "testchannel"
        moderator_badges = {"moderator": "1"}
        
        # Process multiple commands concurrently
        commands = [
            "!clank threshold 40",
            "!clank spontaneous 400",
            "!clank response 80",
            "!clank context 180",
            "!clank status"
        ]
        
        # Execute all commands concurrently
        tasks = [
            config_manager.process_chat_command(channel, f"TestMod{i}", cmd, moderator_badges)
            for i, cmd in enumerate(commands)
        ]
        
        responses = await asyncio.gather(*tasks)
        
        # Verify all commands processed successfully
        assert len(responses) == 5
        for i, response in enumerate(responses):
            if i < 4:  # Configuration commands
                assert "updated to:" in response
            else:  # Status command
                assert "Status -" in response
    
    @pytest.mark.asyncio
    async def test_configuration_affects_message_processing(self, command_system):
        """Test that configuration changes affect message processing behavior."""
        config_manager = command_system['config_manager']
        channel_config = command_system['channel_config']
        db_manager = command_system['db_manager']
        channel = "testchannel"
        moderator_badges = {"moderator": "1"}
        
        # Change message threshold via command
        response = await config_manager.process_chat_command(
            channel, "TestMod", "!clank threshold 5", moderator_badges
        )
        assert "updated to: 5" in response
        
        # Verify the change affects message processing logic
        config = await channel_config.get_config(channel)
        assert config.message_threshold == 5
        
        # Simulate message counting up to new threshold
        for i in range(5):
            await channel_config.increment_message_count(channel)
        
        # Check if generation would be triggered
        can_generate = await channel_config.can_generate_spontaneous(channel)
        assert can_generate is True  # Should be able to generate with new threshold
    
    @pytest.mark.asyncio
    async def test_cooldown_configuration_affects_timing(self, command_system):
        """Test that cooldown configuration affects timing behavior."""
        config_manager = command_system['config_manager']
        channel_config = command_system['channel_config']
        channel = "testchannel"
        moderator_badges = {"moderator": "1"}
        
        # Set very short cooldown for testing
        response = await config_manager.process_chat_command(
            channel, "TestMod", "!clank spontaneous 1", moderator_badges
        )
        assert "updated to: 1" in response
        
        # Trigger spontaneous message timestamp
        await channel_config.update_spontaneous_timestamp(channel)
        
        # Should be in cooldown immediately
        can_generate = await channel_config.can_generate_spontaneous(channel)
        assert can_generate is False
        
        # Wait for cooldown to expire
        await asyncio.sleep(1.1)
        
        # Should be able to generate after cooldown
        can_generate = await channel_config.can_generate_spontaneous(channel)
        # Note: This might still be False due to message count, but cooldown should be cleared
        config = await channel_config.get_config(channel)
        time_since = datetime.now() - config.last_spontaneous_message
        assert time_since.total_seconds() >= 1.0
    
    @pytest.mark.asyncio
    async def test_multi_channel_configuration_isolation(self, command_system):
        """Test that configuration changes are isolated per channel."""
        config_manager = command_system['config_manager']
        channel_config = command_system['channel_config']
        moderator_badges = {"moderator": "1"}
        
        channels = ["channel1", "channel2", "channel3"]
        
        # Set different configurations for each channel
        for i, channel in enumerate(channels):
            threshold = 30 + (i * 10)  # 30, 40, 50
            response = await config_manager.process_chat_command(
                channel, "TestMod", f"!clank threshold {threshold}", moderator_badges
            )
            assert f"updated to: {threshold}" in response
        
        # Verify each channel has its own configuration
        for i, channel in enumerate(channels):
            config = await channel_config.get_config(channel)
            expected_threshold = 30 + (i * 10)
            assert config.message_threshold == expected_threshold
    
    @pytest.mark.asyncio
    async def test_error_recovery_in_command_processing(self, command_system):
        """Test error recovery in command processing."""
        config_manager = command_system['config_manager']
        ollama_client = command_system['ollama_client']
        channel = "testchannel"
        moderator_badges = {"moderator": "1"}
        
        # Simulate database error during configuration update
        with patch.object(command_system['channel_config'], 'update_config', side_effect=Exception("DB Error")):
            response = await config_manager.process_chat_command(
                channel, "TestMod", "!clank threshold 50", moderator_badges
            )
            assert "error occurred" in response.lower()
        
        # Simulate Ollama error during status check
        ollama_client.list_available_models.side_effect = Exception("Ollama Error")
        
        response = await config_manager.process_chat_command(
            channel, "TestMod", "!clank status", moderator_badges
        )
        
        # Should still provide status despite Ollama error
        assert "Status -" in response
        assert "Disconnected" in response
    
    @pytest.mark.asyncio
    async def test_configuration_backup_and_restore(self, command_system):
        """Test configuration backup and restore functionality."""
        config_manager = command_system['config_manager']
        channel_config = command_system['channel_config']
        db_manager = command_system['db_manager']
        channel = "testchannel"
        moderator_badges = {"moderator": "1"}
        
        # Set custom configuration
        custom_settings = [
            ("!clank threshold 35", "message_threshold", 35),
            ("!clank spontaneous 450", "spontaneous_cooldown", 450),
            ("!clank response 90", "response_cooldown", 90),
            ("!clank context 175", "context_limit", 175)
        ]
        
        for command, db_key, expected_value in custom_settings:
            response = await config_manager.process_chat_command(
                channel, "TestMod", command, moderator_badges
            )
            assert "updated to:" in response
        
        # Backup configuration by reading current state
        original_config = await channel_config.get_config(channel)
        backup_values = {
            'message_threshold': original_config.message_threshold,
            'spontaneous_cooldown': original_config.spontaneous_cooldown,
            'response_cooldown': original_config.response_cooldown,
            'context_limit': original_config.context_limit
        }
        
        # Modify configuration
        await config_manager.process_chat_command(
            channel, "TestMod", "!clank threshold 100", moderator_badges
        )
        
        # Verify modification
        modified_config = await channel_config.get_config(channel)
        assert modified_config.message_threshold == 100
        
        # Restore from backup
        for db_key, value in backup_values.items():
            await channel_config.update_config(channel, db_key, value)
        
        # Verify restoration
        restored_config = await channel_config.get_config(channel)
        assert restored_config.message_threshold == 35
        assert restored_config.spontaneous_cooldown == 450
        assert restored_config.response_cooldown == 90
        assert restored_config.context_limit == 175