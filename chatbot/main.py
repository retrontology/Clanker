"""
Main entry point for the Twitch Ollama Chatbot.

This module handles application startup, configuration loading,
and graceful shutdown procedures.
"""

import asyncio
import logging
import signal
import sys
import os
from typing import Optional

from chatbot.config.settings import GlobalConfig, load_global_config
from chatbot.database import create_database_manager, AuthTokenManager
from chatbot.auth import AuthenticationManager, validate_startup_authentication


class ChatbotApplication:
    """Main application class for the Twitch Ollama Chatbot."""
    
    def __init__(self):
        self.config: Optional[GlobalConfig] = None
        self.logger = logging.getLogger(__name__)
        self._shutdown_event = asyncio.Event()
        
        # Core components
        self.db_manager = None
        self.auth_manager = None
    
    async def startup(self) -> None:
        """Initialize the chatbot application."""
        try:
            # Load global configuration
            self.config = load_global_config()
            self.logger.info("Configuration loaded successfully")
            
            # Initialize database connection
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
            
            self.logger.info("Database initialized successfully")
            
            # Initialize authentication manager
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
            
            # TODO: Initialize IRC client
            # TODO: Initialize Ollama client
            # TODO: Initialize message processor
            
            self.logger.info("Chatbot application started successfully")
            
        except Exception as e:
            self.logger.error(f"Failed to start chatbot application: {e}")
            # Ensure cleanup on startup failure
            await self._cleanup_on_failure()
            raise
    
    async def shutdown(self) -> None:
        """Gracefully shutdown the chatbot application."""
        self.logger.info("Shutting down chatbot application...")
        
        # TODO: Close IRC connections
        
        # Close authentication manager
        if self.auth_manager:
            try:
                await self.auth_manager.close()
                self.logger.info("Authentication manager closed")
            except Exception as e:
                self.logger.error(f"Error closing authentication manager: {e}")
        
        # TODO: Close database connections
        # TODO: Save persistent state
        
        self.logger.info("Chatbot application shutdown complete")
    
    async def _cleanup_on_failure(self) -> None:
        """Cleanup resources on startup failure."""
        try:
            if self.auth_manager:
                await self.auth_manager.close()
        except Exception as e:
            self.logger.error(f"Error during cleanup: {e}")
    
    async def run(self) -> None:
        """Run the main application loop."""
        await self.startup()
        
        # Wait for shutdown signal
        await self._shutdown_event.wait()
        
        await self.shutdown()
    
    def signal_handler(self, signum: int, frame) -> None:
        """Handle shutdown signals."""
        self.logger.info(f"Received signal {signum}, initiating shutdown...")
        self._shutdown_event.set()


async def main() -> None:
    """Main entry point."""
    # Set up basic logging
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