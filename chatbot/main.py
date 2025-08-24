"""
Main entry point for the Twitch Ollama Chatbot.

This module handles application startup, configuration loading,
component initialization, and graceful shutdown procedures.
"""

import asyncio
import logging
import signal
import sys
import os
from typing import Optional

from chatbot.config.settings import GlobalConfig, load_global_config, validate_config, ConfigurationSystem
from chatbot.database import create_database_manager, AuthTokenManager, ChannelConfigManager
from chatbot.auth import AuthenticationManager, validate_startup_authentication
from chatbot.irc.client import TwitchIRCClient
from chatbot.ollama.client import OllamaClient
from chatbot.processing.coordinator import MessageProcessor
from chatbot.processing.integration import FilteredMessageProcessor
from chatbot.processing.filters import ContentFilter
from chatbot.logging.logger import get_logger
from chatbot.logging.metrics import MetricsManager
from chatbot.resource_manager import ResourceManager, ResourceThresholds


class ChatbotApplication:
    """Main application class for the Twitch Ollama Chatbot."""
    
    def __init__(self):
        self.config: Optional[GlobalConfig] = None
        self.logger = None  # Will be initialized after config loading
        self._shutdown_event = asyncio.Event()
        
        # Core components
        self.db_manager = None
        self.auth_manager = None
        self.config_manager = None
        self.config_system = None
        self.metrics_manager = None
        self.resource_manager = None
        self.content_filter = None
        self.ollama_client = None
        self.irc_client = None
        self.message_processor = None
        self.filtered_processor = None
        
        # Component initialization tracking
        self._initialized_components = []
    
    async def startup(self) -> None:
        """Initialize the chatbot application with proper component initialization order."""
        try:
            # Step 1: Load and validate global configuration
            await self._initialize_configuration()
            
            # Step 2: Set up structured logging
            await self._initialize_logging()
            
            # Step 3: Initialize database layer
            await self._initialize_database()
            
            # Step 4: Initialize authentication
            await self._initialize_authentication()
            
            # Step 5: Initialize content filtering
            await self._initialize_content_filter()
            
            # Step 6: Initialize Ollama client
            await self._initialize_ollama_client()
            
            # Step 7: Initialize IRC client
            await self._initialize_irc_client()
            
            # Step 8: Initialize message processing
            await self._initialize_message_processor()
            
            # Step 9: Initialize resource manager
            await self._initialize_resource_manager()
            
            # Step 10: Load persistent state
            await self._load_persistent_state()
            
            # Step 11: Start IRC connection
            await self._start_irc_connection()
            
            # Step 12: Start resource monitoring
            await self._start_resource_monitoring()
            
            self.logger.info(
                "Chatbot application started successfully",
                channels=self.config.channels,
                database_type=self.config.database_type,
                ollama_model=self.config.ollama_model,
                content_filter_enabled=self.config.content_filter_enabled
            )
            
        except Exception as e:
            if self.logger:
                self.logger.error(f"Failed to start chatbot application: {e}")
            else:
                print(f"Failed to start chatbot application: {e}")
            
            # Ensure cleanup on startup failure
            await self._cleanup_on_failure()
            raise
    
    async def _initialize_configuration(self) -> None:
        """Load and validate global configuration."""
        self.config = load_global_config()
        validate_config(self.config)
        self._initialized_components.append("configuration")
    
    async def _initialize_logging(self) -> None:
        """Set up structured logging system."""
        self.logger = get_logger(
            "chatbot.main",
            level=self.config.log_level,
            format_type=self.config.log_format,
            log_file=os.getenv('LOG_FILE')
        )
        
        self.logger.info(
            "Logging system initialized",
            log_level=self.config.log_level,
            log_format=self.config.log_format
        )
        self._initialized_components.append("logging")
    
    async def _initialize_database(self) -> None:
        """Initialize database connection and managers."""
        self.logger.info("Initializing database connection...")
        
        config_dict = {
            'DATABASE_TYPE': self.config.database_type,
            'DATABASE_URL': self.config.database_url,
            'MYSQL_HOST': self.config.mysql_host,
            'MYSQL_PORT': str(self.config.mysql_port),
            'MYSQL_USER': self.config.mysql_user,
            'MYSQL_PASSWORD': self.config.mysql_password,
            'MYSQL_DATABASE': self.config.mysql_database
        }
        
        self.db_manager = create_database_manager(config_dict)
        if not await self.db_manager.initialize():
            raise RuntimeError("Failed to initialize database")
        
        # Initialize channel configuration manager
        self.config_manager = ChannelConfigManager(self.db_manager)
        
        # Initialize metrics manager
        self.metrics_manager = MetricsManager(self.db_manager)
        
        # Initialize configuration system
        self.config_system = ConfigurationSystem(self.config, self.config_manager)
        
        self.logger.info(
            "Database initialized successfully",
            database_type=self.config.database_type
        )
        self._initialized_components.append("database")
    
    async def _initialize_authentication(self) -> None:
        """Initialize authentication manager and validate tokens."""
        self.logger.info("Initializing authentication manager...")
        
        auth_token_manager = AuthTokenManager(self.db_manager)
        encryption_key = os.getenv('TOKEN_ENCRYPTION_KEY')  # Optional encryption key
        
        self.auth_manager = AuthenticationManager(
            client_id=self.config.twitch_client_id,
            client_secret=self.config.twitch_client_secret,
            auth_token_manager=auth_token_manager,
            encryption_key=encryption_key
        )
        
        # Validate authentication during startup
        self.logger.info("Validating authentication...")
        if not await validate_startup_authentication(self.auth_manager):
            raise RuntimeError("Authentication validation failed")
        
        self.logger.info("Authentication validated successfully")
        self._initialized_components.append("authentication")
    
    async def _initialize_content_filter(self) -> None:
        """Initialize content filtering system."""
        if not self.config.content_filter_enabled:
            self.logger.warning("Content filtering is disabled")
            self.content_filter = None
            return
        
        self.logger.info("Initializing content filter...")
        
        self.content_filter = ContentFilter(self.config.blocked_words_file)
        
        # Load blocked words
        if not self.content_filter.load_blocked_words():
            self.logger.warning(
                "Failed to load blocked words file, using empty filter",
                blocked_words_file=self.config.blocked_words_file
            )
        
        self.logger.info(
            "Content filter initialized",
            blocked_words_count=len(self.content_filter.blocked_words) if self.content_filter.blocked_words else 0
        )
        self._initialized_components.append("content_filter")
    
    async def _initialize_ollama_client(self) -> None:
        """Initialize Ollama client and validate startup model."""
        self.logger.info("Initializing Ollama client...")
        
        self.ollama_client = OllamaClient(
            base_url=self.config.ollama_url,
            timeout=self.config.ollama_timeout
        )
        
        # Validate startup model availability
        try:
            await self.ollama_client.validate_startup_model(self.config.ollama_model)
            self.logger.info(
                "Ollama client initialized and model validated",
                ollama_url=self.config.ollama_url,
                default_model=self.config.ollama_model
            )
        except Exception as e:
            raise RuntimeError(f"Ollama model validation failed: {e}")
        
        self._initialized_components.append("ollama_client")
    
    async def _initialize_irc_client(self) -> None:
        """Initialize Twitch IRC client."""
        self.logger.info("Initializing IRC client...")
        
        # Get bot username from authentication
        bot_username = await self.auth_manager.get_bot_username()
        if not bot_username:
            raise RuntimeError("Could not determine bot username from authentication")
        
        # Get access token
        access_token = await self.auth_manager.get_valid_access_token()
        if not access_token:
            raise RuntimeError("Could not get valid access token")
        
        self.irc_client = TwitchIRCClient(
            token=access_token,
            bot_username=bot_username,
            initial_channels=self.config.channels,
            db_manager=self.db_manager,
            config_manager=self.config_manager,
            content_filter=self.content_filter
        )
        
        self.logger.info(
            "IRC client initialized",
            bot_username=bot_username,
            channels=self.config.channels
        )
        self._initialized_components.append("irc_client")
    
    async def _initialize_message_processor(self) -> None:
        """Initialize message processing coordinator."""
        self.logger.info("Initializing message processor...")
        
        # Initialize filtered message processor
        self.filtered_processor = FilteredMessageProcessor(
            content_filter=self.content_filter,
            metrics_manager=self.metrics_manager
        )
        
        # Initialize main message processor
        self.message_processor = MessageProcessor(
            db_manager=self.db_manager,
            config_manager=self.config_manager,
            ollama_client=self.ollama_client,
            filtered_processor=self.filtered_processor,
            default_model=self.config.ollama_model
        )
        
        # Set up message sender callback
        self.message_processor.set_message_sender(self.irc_client.send_message)
        
        # Connect IRC client to message processor
        self.irc_client.add_message_handler(self.message_processor.process_incoming_message)
        self.irc_client.add_moderation_handler(self.message_processor.handle_moderation_event)
        
        self.logger.info("Message processor initialized")
        self._initialized_components.append("message_processor")
    
    async def _initialize_resource_manager(self) -> None:
        """Initialize resource manager with configurable thresholds."""
        self.logger.info("Initializing resource manager...")
        
        # Load resource thresholds from environment variables
        thresholds = ResourceThresholds(
            memory_warning_mb=int(os.getenv('MEMORY_WARNING_MB', '512')),
            memory_critical_mb=int(os.getenv('MEMORY_CRITICAL_MB', '1024')),
            disk_warning_percent=int(os.getenv('DISK_WARNING_PERCENT', '85')),
            disk_critical_percent=int(os.getenv('DISK_CRITICAL_PERCENT', '95')),
            message_retention_days=int(os.getenv('MESSAGE_RETENTION_DAYS', '30')),
            metrics_retention_days=int(os.getenv('METRICS_RETENTION_DAYS', '7')),
            cleanup_interval_minutes=int(os.getenv('CLEANUP_INTERVAL_MINUTES', '60'))
        )
        
        self.resource_manager = ResourceManager(
            db_manager=self.db_manager,
            config_manager=self.config_manager,
            metrics_manager=self.metrics_manager,
            thresholds=thresholds
        )
        
        self.logger.info(
            "Resource manager initialized",
            memory_warning_mb=thresholds.memory_warning_mb,
            memory_critical_mb=thresholds.memory_critical_mb,
            cleanup_interval_minutes=thresholds.cleanup_interval_minutes
        )
        self._initialized_components.append("resource_manager")
    
    async def _load_persistent_state(self) -> None:
        """Load persistent state for all channels."""
        self.logger.info("Loading persistent state...")
        
        # Initialize channel configurations
        if not await self.config_system.initialize_channel_configs():
            self.logger.warning("Some channel configurations failed to initialize")
        
        # Load persistent state
        if not await self.config_system.load_persistent_state():
            self.logger.warning("Some persistent state failed to load")
        
        self.logger.info("Persistent state loaded")
        self._initialized_components.append("persistent_state")
    
    async def _start_irc_connection(self) -> None:
        """Start IRC connection in background."""
        self.logger.info("Starting IRC connection...")
        
        # Start IRC client in background
        asyncio.create_task(self.irc_client.start())
        
        # Give it a moment to connect
        await asyncio.sleep(2)
        
        self.logger.info("IRC connection started")
        self._initialized_components.append("irc_connection")
    
    async def _start_resource_monitoring(self) -> None:
        """Start resource monitoring and cleanup tasks."""
        self.logger.info("Starting resource monitoring...")
        
        if self.resource_manager:
            await self.resource_manager.start_monitoring()
            self.logger.info("Resource monitoring started")
        
        self._initialized_components.append("resource_monitoring")
    
    async def shutdown(self) -> None:
        """Gracefully shutdown the chatbot application with cleanup and state persistence."""
        if self.logger:
            self.logger.info("Shutting down chatbot application...")
        
        # Step 1: Save persistent state
        await self._save_persistent_state()
        
        # Step 2: Close IRC connections
        await self._shutdown_irc_client()
        
        # Step 3: Shutdown message processor
        await self._shutdown_message_processor()
        
        # Step 4: Close Ollama client
        await self._shutdown_ollama_client()
        
        # Step 5: Shutdown resource manager
        await self._shutdown_resource_manager()
        
        # Step 6: Shutdown metrics manager
        await self._shutdown_metrics_manager()
        
        # Step 7: Close authentication manager
        await self._shutdown_authentication()
        
        # Step 8: Close database connections
        await self._shutdown_database()
        
        if self.logger:
            self.logger.info("Chatbot application shutdown complete")
    
    async def _save_persistent_state(self) -> None:
        """Save persistent state for all channels."""
        try:
            if self.config_system:
                await self.config_system.save_persistent_state()
                if self.logger:
                    self.logger.info("Persistent state saved")
        except Exception as e:
            if self.logger:
                self.logger.error(f"Error saving persistent state: {e}")
    
    async def _shutdown_irc_client(self) -> None:
        """Shutdown IRC client."""
        try:
            if self.irc_client:
                await self.irc_client.close()
                if self.logger:
                    self.logger.info("IRC client closed")
        except Exception as e:
            if self.logger:
                self.logger.error(f"Error closing IRC client: {e}")
    
    async def _shutdown_message_processor(self) -> None:
        """Shutdown message processor."""
        try:
            # Message processor doesn't need explicit shutdown currently
            # but this is here for future enhancements
            if self.logger:
                self.logger.info("Message processor shutdown")
        except Exception as e:
            if self.logger:
                self.logger.error(f"Error shutting down message processor: {e}")
    
    async def _shutdown_ollama_client(self) -> None:
        """Shutdown Ollama client."""
        try:
            if self.ollama_client:
                await self.ollama_client.close()
                if self.logger:
                    self.logger.info("Ollama client closed")
        except Exception as e:
            if self.logger:
                self.logger.error(f"Error closing Ollama client: {e}")
    
    async def _shutdown_resource_manager(self) -> None:
        """Shutdown resource manager."""
        try:
            if self.resource_manager:
                await self.resource_manager.shutdown()
                if self.logger:
                    self.logger.info("Resource manager shutdown")
        except Exception as e:
            if self.logger:
                self.logger.error(f"Error shutting down resource manager: {e}")
    
    async def _shutdown_metrics_manager(self) -> None:
        """Shutdown metrics manager."""
        try:
            if self.metrics_manager:
                await self.metrics_manager.shutdown()
                if self.logger:
                    self.logger.info("Metrics manager shutdown")
        except Exception as e:
            if self.logger:
                self.logger.error(f"Error shutting down metrics manager: {e}")
    
    async def _shutdown_authentication(self) -> None:
        """Shutdown authentication manager."""
        try:
            if self.auth_manager:
                await self.auth_manager.close()
                if self.logger:
                    self.logger.info("Authentication manager closed")
        except Exception as e:
            if self.logger:
                self.logger.error(f"Error closing authentication manager: {e}")
    
    async def _shutdown_database(self) -> None:
        """Shutdown database connections."""
        try:
            if self.db_manager:
                await self.db_manager.close()
                if self.logger:
                    self.logger.info("Database connections closed")
        except Exception as e:
            if self.logger:
                self.logger.error(f"Error closing database connections: {e}")
    
    async def _cleanup_on_failure(self) -> None:
        """Cleanup resources on startup failure."""
        try:
            # Clean up in reverse order of initialization
            components_to_cleanup = list(reversed(self._initialized_components))
            
            for component in components_to_cleanup:
                try:
                    if component == "resource_monitoring" and self.resource_manager:
                        await self.resource_manager.stop_monitoring()
                    elif component == "irc_connection" and self.irc_client:
                        await self.irc_client.close()
                    elif component == "ollama_client" and self.ollama_client:
                        await self.ollama_client.close()
                    elif component == "resource_manager" and self.resource_manager:
                        await self.resource_manager.shutdown()
                    elif component == "authentication" and self.auth_manager:
                        await self.auth_manager.close()
                    elif component == "database" and self.db_manager:
                        await self.db_manager.close()
                    # Other components don't need explicit cleanup
                except Exception as cleanup_error:
                    if self.logger:
                        self.logger.error(f"Error cleaning up {component}: {cleanup_error}")
                    
        except Exception as e:
            if self.logger:
                self.logger.error(f"Error during cleanup: {e}")
    
    async def run(self) -> None:
        """Run the main application loop."""
        await self.startup()
        
        # Wait for shutdown signal
        await self._shutdown_event.wait()
        
        await self.shutdown()
    
    def signal_handler(self, signum: int, frame) -> None:
        """Handle shutdown signals."""
        if self.logger:
            self.logger.info(f"Received signal {signum}, initiating shutdown...")
        else:
            print(f"Received signal {signum}, initiating shutdown...")
        self._shutdown_event.set()


async def main() -> None:
    """Main entry point with startup validation."""
    # Set up basic logging for startup
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s %(levelname)s [%(name)s] %(message)s'
    )
    
    app = ChatbotApplication()
    
    # Set up signal handlers for graceful shutdown
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, app.signal_handler)
    
    try:
        await app.run()
    except KeyboardInterrupt:
        logging.info("Received keyboard interrupt, shutting down...")
    except Exception as e:
        logging.error(f"Application error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())