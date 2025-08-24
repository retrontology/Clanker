"""
Main entry point for the Twitch Ollama Chatbot.

This module handles application startup, configuration loading,
and graceful shutdown procedures.
"""

import asyncio
import logging
import signal
import sys
from typing import Optional

from chatbot.config.settings import GlobalConfig, load_global_config


class ChatbotApplication:
    """Main application class for the Twitch Ollama Chatbot."""
    
    def __init__(self):
        self.config: Optional[GlobalConfig] = None
        self.logger = logging.getLogger(__name__)
        self._shutdown_event = asyncio.Event()
    
    async def startup(self) -> None:
        """Initialize the chatbot application."""
        try:
            # Load global configuration
            self.config = load_global_config()
            self.logger.info("Configuration loaded successfully")
            
            # TODO: Initialize database connection
            # TODO: Initialize authentication manager
            # TODO: Initialize IRC client
            # TODO: Initialize Ollama client
            # TODO: Initialize message processor
            
            self.logger.info("Chatbot application started successfully")
            
        except Exception as e:
            self.logger.error(f"Failed to start chatbot application: {e}")
            raise
    
    async def shutdown(self) -> None:
        """Gracefully shutdown the chatbot application."""
        self.logger.info("Shutting down chatbot application...")
        
        # TODO: Close IRC connections
        # TODO: Close database connections
        # TODO: Save persistent state
        
        self.logger.info("Chatbot application shutdown complete")
    
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