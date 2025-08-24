"""
Chat command handling for the Twitch Ollama Chatbot.

This module handles parsing and processing of !clank commands
for configuration management.
"""

import logging
import re
from typing import Dict, List, Optional, Tuple, Any
from datetime import datetime

from ..database.operations import ChannelConfigManager
from ..ollama.client import OllamaClient

logger = logging.getLogger(__name__)


class ConfigurationManager:
    """Manages chat command processing and configuration validation."""
    
    def __init__(self, channel_config_manager: ChannelConfigManager, ollama_client: OllamaClient):
        """
        Initialize ConfigurationManager.
        
        Args:
            channel_config_manager: ChannelConfigManager instance
            ollama_client: OllamaClient instance for model validation
        """
        self.channel_config = channel_config_manager
        self.ollama_client = ollama_client
        
        # Valid configuration keys and their descriptions
        self.valid_settings = {
            'threshold': {
                'description': 'Message count threshold for spontaneous generation',
                'type': int,
                'min': 1,
                'max': 1000,
                'db_key': 'message_threshold'
            },
            'spontaneous': {
                'description': 'Cooldown in seconds between spontaneous messages',
                'type': int,
                'min': 0,
                'max': 3600,
                'db_key': 'spontaneous_cooldown'
            },
            'response': {
                'description': 'Cooldown in seconds between responses to same user',
                'type': int,
                'min': 0,
                'max': 3600,
                'db_key': 'response_cooldown'
            },
            'context': {
                'description': 'Maximum number of messages in context window',
                'type': int,
                'min': 10,
                'max': 1000,
                'db_key': 'context_limit'
            },
            'model': {
                'description': 'Ollama model to use for this channel',
                'type': str,
                'db_key': 'ollama_model'
            }
        }
    
    async def process_chat_command(self, channel: str, user_display_name: str, 
                                 command: str, badges: Dict[str, str]) -> str:
        """
        Process a !clank chat command.
        
        Args:
            channel: Channel name
            user_display_name: User's display name
            command: Full command string (including !clank)
            badges: User's Twitch IRC badges
            
        Returns:
            str: Response message to send to chat
        """
        try:
            # Check user authorization
            if not await self.check_user_permissions(channel, user_display_name, badges):
                return f"@{user_display_name} You need to be a moderator or broadcaster to use !clank commands."
            
            # Parse command
            parts = command.strip().split()
            if len(parts) < 2:
                return await self._show_help(user_display_name)
            
            command_name = parts[1].lower()
            
            # Handle status command separately
            if command_name == 'status':
                return await self._handle_status_command(channel, user_display_name)
            
            # Handle configuration commands
            if command_name in self.valid_settings:
                if len(parts) == 2:
                    # Show current value
                    return await self._show_setting(channel, user_display_name, command_name)
                elif len(parts) == 3:
                    # Set new value
                    return await self._set_setting(channel, user_display_name, command_name, parts[2])
                else:
                    return f"@{user_display_name} Usage: !clank {command_name} [value]"
            else:
                return await self._show_help(user_display_name)
                
        except Exception as e:
            logger.error(f"Error processing command '{command}' from {user_display_name} in {channel}: {e}")
            return f"@{user_display_name} An error occurred processing your command."
    
    async def check_user_permissions(self, channel: str, user_display_name: str, 
                                   badges: Dict[str, str]) -> bool:
        """
        Check if user has permission to modify configuration.
        
        Args:
            channel: Channel name
            user_display_name: User's display name
            badges: User's Twitch IRC badges
            
        Returns:
            bool: True if user has permission, False otherwise
        """
        return self.is_channel_owner_or_mod(badges)
    
    def is_channel_owner_or_mod(self, badges: Dict[str, str]) -> bool:
        """
        Check if user is channel owner or moderator based on IRC badges.
        
        Args:
            badges: User's Twitch IRC badges
            
        Returns:
            bool: True if user is broadcaster or moderator
        """
        # Check for broadcaster badge (channel owner)
        if 'broadcaster' in badges:
            return True
        
        # Check for moderator badge
        if 'moderator' in badges:
            return True
        
        return False
    
    async def _show_help(self, user_display_name: str) -> str:
        """Show help message with available commands."""
        help_text = f"@{user_display_name} Available !clank commands: " + ", ".join(self.valid_settings.keys()) + ", status"
        return help_text
    
    async def _show_setting(self, channel: str, user_display_name: str, setting: str) -> str:
        """Show current value of a configuration setting."""
        try:
            config = await self.channel_config.get_config(channel)
            setting_info = self.valid_settings[setting]
            db_key = setting_info['db_key']
            
            current_value = getattr(config, db_key)
            if current_value is None and setting == 'model':
                current_value = "default (global)"
            
            return f"@{user_display_name} {setting}: {current_value} - {setting_info['description']}"
            
        except Exception as e:
            logger.error(f"Error showing setting {setting} for {channel}: {e}")
            return f"@{user_display_name} Error retrieving {setting} setting."
    
    async def _set_setting(self, channel: str, user_display_name: str, 
                          setting: str, value_str: str) -> str:
        """Set a configuration setting to a new value."""
        try:
            setting_info = self.valid_settings[setting]
            
            # Validate and convert value
            validation_result = await self.validate_setting_value(setting, value_str)
            if not validation_result[0]:
                return f"@{user_display_name} {validation_result[1]}"
            
            converted_value = validation_result[2]
            
            # Special handling for model setting
            if setting == 'model':
                model_validation = await self.validate_model_change(converted_value)
                if not model_validation[0]:
                    return f"@{user_display_name} {model_validation[1]}"
            
            # Update the setting
            db_key = setting_info['db_key']
            success = await self.channel_config.update_config(channel, db_key, converted_value)
            
            if success:
                logger.info(f"Configuration updated", extra={
                    'channel': channel,
                    'setting': setting,
                    'value': converted_value,
                    'changed_by': user_display_name
                })
                return f"@{user_display_name} {setting} updated to: {converted_value}"
            else:
                return f"@{user_display_name} Failed to update {setting} setting."
                
        except Exception as e:
            logger.error(f"Error setting {setting}={value_str} for {channel}: {e}")
            return f"@{user_display_name} Error updating {setting} setting."
    
    async def validate_setting_value(self, key: str, value_str: str) -> Tuple[bool, str, Any]:
        """
        Validate a configuration setting value.
        
        Args:
            key: Setting key
            value_str: String value to validate
            
        Returns:
            Tuple of (is_valid, error_message, converted_value)
        """
        if key not in self.valid_settings:
            return False, f"Unknown setting: {key}", None
        
        setting_info = self.valid_settings[key]
        
        try:
            if setting_info['type'] == int:
                value = int(value_str)
                
                # Check range if specified
                if 'min' in setting_info and value < setting_info['min']:
                    return False, f"{key} must be at least {setting_info['min']}", None
                if 'max' in setting_info and value > setting_info['max']:
                    return False, f"{key} must be at most {setting_info['max']}", None
                
                return True, "", value
                
            elif setting_info['type'] == str:
                value = value_str.strip()
                
                # Special validation for model names
                if key == 'model':
                    if value.lower() in ['default', 'global', 'none', '']:
                        return True, "", None  # Use global default
                    
                    # Basic model name validation
                    if not re.match(r'^[a-zA-Z0-9._-]+$', value):
                        return False, "Model name contains invalid characters", None
                
                return True, "", value
            
            else:
                return False, f"Unsupported setting type for {key}", None
                
        except ValueError as e:
            return False, f"Invalid value for {key}: {value_str}", None
    
    async def validate_model_change(self, model_name: Optional[str]) -> Tuple[bool, str]:
        """
        Validate that a model is available on Ollama server.
        
        Args:
            model_name: Model name to validate (None for default)
            
        Returns:
            Tuple of (is_valid, message)
        """
        if model_name is None:
            return True, "Using global default model"
        
        try:
            # Check if model is available
            is_available = await self.ollama_client.validate_model(model_name)
            
            if is_available:
                return True, f"Model {model_name} is available"
            else:
                available_models = await self.ollama_client.list_available_models()
                if available_models:
                    models_list = ", ".join(available_models[:5])  # Show first 5 models
                    return False, f"Model {model_name} not found. Available models: {models_list}"
                else:
                    return False, f"Model {model_name} not found and could not retrieve available models"
                    
        except Exception as e:
            logger.warning(f"Could not validate model {model_name}: {e}")
            # Allow the change but warn
            return True, f"Model {model_name} set (validation unavailable)"
    
    async def _handle_status_command(self, channel: str, user_display_name: str) -> str:
        """Handle !clank status command with comprehensive system health reporting."""
        try:
            # Get channel configuration
            config = await self.channel_config.get_config(channel)
            
            # Get Ollama connectivity and model information
            ollama_status, model_info, response_time = await self._get_ollama_status(config)
            
            # Get performance metrics if available
            performance_info = await self._get_performance_info(channel)
            
            # Calculate cooldown status
            cooldown_info = await self._get_cooldown_status(config)
            
            # Format comprehensive status response
            status_parts = [
                f"Ollama: {ollama_status}",
                f"Model: {model_info}",
                f"Messages: {config.message_count}/{config.message_threshold}",
                f"Cooldowns: {cooldown_info}",
            ]
            
            if response_time:
                status_parts.append(f"Response: {response_time}ms")
            
            if performance_info:
                status_parts.append(performance_info)
            
            return f"@{user_display_name} Status - " + " | ".join(status_parts)
            
        except Exception as e:
            logger.error(f"Error handling status command for {channel}: {e}")
            return f"@{user_display_name} Error retrieving status information."
    
    async def _get_ollama_status(self, config) -> tuple:
        """Get Ollama connectivity status and model information."""
        try:
            start_time = datetime.now()
            available_models = await self.ollama_client.list_available_models()
            response_time = int((datetime.now() - start_time).total_seconds() * 1000)
            
            if available_models:
                current_model = config.ollama_model or "default"
                
                # Check if current model is available
                if config.ollama_model and config.ollama_model not in available_models:
                    model_status = f"{current_model} (NOT FOUND)"
                    ollama_status = "Connected (model issue)"
                else:
                    model_status = f"{current_model}"
                    ollama_status = "Connected"
                
                model_info = f"{model_status} ({len(available_models)} available)"
                return ollama_status, model_info, response_time
            else:
                return "Connected (no models)", "No models available", response_time
                
        except Exception as e:
            error_msg = str(e)[:30] + "..." if len(str(e)) > 30 else str(e)
            return "Disconnected", f"Error: {error_msg}", None
    
    async def _get_performance_info(self, channel: str) -> Optional[str]:
        """Get performance information if metrics manager is available."""
        try:
            # Try to get metrics manager from channel config manager
            if hasattr(self.channel_config, 'db_manager'):
                from ..database.operations import MetricsManager
                metrics_manager = MetricsManager(self.channel_config.db_manager)
                
                # Get recent performance stats (last 24 hours)
                stats = await metrics_manager.get_performance_stats(channel, hours=24)
                
                if stats:
                    perf_parts = []
                    
                    # Response time stats
                    if 'response_time' in stats:
                        avg_time = stats['response_time']['average']
                        perf_parts.append(f"Avg: {avg_time:.1f}s")
                    
                    # Success/error counts
                    success_count = stats.get('success_count', {}).get('count', 0)
                    error_counts = sum(
                        stat['count'] for key, stat in stats.items() 
                        if key.startswith('error_')
                    )
                    
                    if success_count > 0 or error_counts > 0:
                        total_ops = success_count + error_counts
                        success_rate = (success_count / total_ops * 100) if total_ops > 0 else 0
                        perf_parts.append(f"Success: {success_rate:.0f}%")
                    
                    if perf_parts:
                        return "Perf: " + " ".join(perf_parts)
            
            return None
            
        except Exception as e:
            logger.debug(f"Could not get performance info for {channel}: {e}")
            return None
    
    async def _get_cooldown_status(self, config) -> str:
        """Get cooldown status information."""
        try:
            cooldown_parts = []
            
            # Spontaneous cooldown status
            if config.last_spontaneous_message:
                time_since = datetime.now() - config.last_spontaneous_message
                remaining = max(0, config.spontaneous_cooldown - int(time_since.total_seconds()))
                if remaining > 0:
                    cooldown_parts.append(f"Spont: {remaining}s")
                else:
                    cooldown_parts.append("Spont: Ready")
            else:
                cooldown_parts.append("Spont: Ready")
            
            # Response cooldown (general info)
            cooldown_parts.append(f"Resp: {config.response_cooldown}s")
            
            return " ".join(cooldown_parts)
            
        except Exception as e:
            logger.debug(f"Error getting cooldown status: {e}")
            return f"{config.spontaneous_cooldown}s/{config.response_cooldown}s"