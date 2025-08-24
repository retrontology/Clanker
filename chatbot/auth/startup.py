"""
Startup authentication validation module.

This module handles authentication validation during bot startup
with clear error messaging and graceful failure handling.
"""

import logging
import sys
from typing import Optional, Tuple
from .manager import AuthenticationManager

logger = logging.getLogger(__name__)


class StartupAuthValidator:
    """Handles authentication validation during bot startup."""
    
    def __init__(self, auth_manager: AuthenticationManager):
        """
        Initialize StartupAuthValidator.
        
        Args:
            auth_manager: AuthenticationManager instance
        """
        self.auth_manager = auth_manager
    
    async def validate_startup_authentication(self) -> Tuple[bool, Optional[str]]:
        """
        Validate authentication during startup with comprehensive error handling.
        
        Returns:
            Tuple[bool, Optional[str]]: (success, error_message)
        """
        try:
            logger.info("Starting authentication validation...")
            
            # Step 1: Try to load stored tokens
            logger.info("Loading stored authentication tokens...")
            if not await self.auth_manager.load_stored_tokens():
                error_msg = (
                    "No valid authentication tokens found. Please run the initial "
                    "OAuth setup to authenticate your bot account."
                )
                logger.error(error_msg)
                return False, error_msg
            
            # Step 2: Validate authentication with Twitch
            logger.info("Validating authentication with Twitch...")
            if not await self.auth_manager.validate_authentication():
                error_msg = (
                    "Authentication validation failed. Your tokens may be invalid "
                    "or expired. Please re-authenticate your bot account."
                )
                logger.error(error_msg)
                return False, error_msg
            
            # Step 3: Verify bot username is available
            bot_username = self.auth_manager.get_bot_username()
            if not bot_username:
                error_msg = (
                    "Could not determine bot username from authentication tokens. "
                    "Please re-authenticate your bot account."
                )
                logger.error(error_msg)
                return False, error_msg
            
            # Success
            logger.info(f"Authentication validation successful for bot: {bot_username}")
            return True, None
            
        except Exception as e:
            error_msg = f"Unexpected error during authentication validation: {e}"
            logger.error(error_msg)
            return False, error_msg
    
    async def attempt_token_refresh(self) -> Tuple[bool, Optional[str]]:
        """
        Attempt to refresh tokens if validation fails.
        
        Returns:
            Tuple[bool, Optional[str]]: (success, error_message)
        """
        try:
            logger.info("Attempting token refresh...")
            
            # Try to ensure we have a valid token (this will attempt refresh)
            access_token = await self.auth_manager.ensure_valid_token()
            if access_token:
                logger.info("Token refresh successful")
                return True, None
            else:
                error_msg = (
                    "Token refresh failed. Your refresh token may be invalid "
                    "or expired. Please re-authenticate your bot account."
                )
                logger.error(error_msg)
                return False, error_msg
                
        except Exception as e:
            error_msg = f"Token refresh error: {e}"
            logger.error(error_msg)
            return False, error_msg
    
    async def handle_authentication_failure(self, error_message: str) -> None:
        """
        Handle authentication failure with clear error messaging and graceful shutdown.
        
        Args:
            error_message: Error message to display
        """
        logger.error("=" * 60)
        logger.error("AUTHENTICATION FAILURE")
        logger.error("=" * 60)
        logger.error(error_message)
        logger.error("")
        logger.error("To resolve this issue:")
        logger.error("1. Ensure your Twitch application credentials are correct")
        logger.error("2. Run the OAuth setup process to authenticate your bot")
        logger.error("3. Verify your bot account has the required permissions")
        logger.error("4. Check that your tokens haven't been revoked")
        logger.error("=" * 60)
        
        # Log authentication event for monitoring
        logger.error("Bot startup failed due to authentication failure", extra={
            'event_type': 'startup_auth_failure',
            'error_message': error_message,
            'timestamp': logger.handlers[0].formatter.formatTime(logger.makeRecord(
                'startup', logging.ERROR, __file__, 0, '', (), None
            )) if logger.handlers else None
        })
    
    async def log_authentication_success(self) -> None:
        """Log successful authentication for monitoring."""
        bot_username = self.auth_manager.get_bot_username()
        
        logger.info("Authentication validation completed successfully")
        logger.info(f"Bot authenticated as: {bot_username}")
        
        # Log authentication event for monitoring
        logger.info("Bot startup authentication successful", extra={
            'event_type': 'startup_auth_success',
            'bot_username': bot_username,
            'timestamp': logger.handlers[0].formatter.formatTime(logger.makeRecord(
                'startup', logging.INFO, __file__, 0, '', (), None
            )) if logger.handlers else None
        })
    
    async def validate_with_retry(self, max_retries: int = 2) -> bool:
        """
        Validate authentication with retry logic.
        
        Args:
            max_retries: Maximum number of retry attempts
            
        Returns:
            bool: True if validation successful, False otherwise
        """
        for attempt in range(max_retries + 1):
            try:
                if attempt > 0:
                    logger.info(f"Authentication validation attempt {attempt + 1}/{max_retries + 1}")
                
                # First attempt: normal validation
                success, error_msg = await self.validate_startup_authentication()
                if success:
                    await self.log_authentication_success()
                    return True
                
                # If first attempt fails, try token refresh
                if attempt < max_retries:
                    logger.info("Initial validation failed, attempting token refresh...")
                    refresh_success, refresh_error = await self.attempt_token_refresh()
                    if refresh_success:
                        # Retry validation after refresh
                        success, error_msg = await self.validate_startup_authentication()
                        if success:
                            await self.log_authentication_success()
                            return True
                    else:
                        logger.warning(f"Token refresh failed: {refresh_error}")
                
                # Log the error for this attempt
                if error_msg:
                    logger.warning(f"Authentication attempt {attempt + 1} failed: {error_msg}")
                
            except Exception as e:
                logger.error(f"Authentication attempt {attempt + 1} error: {e}")
        
        # All attempts failed
        final_error = "Authentication validation failed after all retry attempts"
        await self.handle_authentication_failure(final_error)
        return False
    
    async def perform_startup_validation(self) -> bool:
        """
        Perform complete startup authentication validation.
        
        This is the main entry point for startup authentication validation.
        
        Returns:
            bool: True if authentication is valid and bot can start, False otherwise
        """
        try:
            logger.info("Beginning startup authentication validation...")
            
            # Validate with retry logic
            if await self.validate_with_retry():
                logger.info("Startup authentication validation completed successfully")
                return True
            else:
                logger.error("Startup authentication validation failed")
                return False
                
        except Exception as e:
            error_msg = f"Critical error during startup authentication: {e}"
            logger.error(error_msg)
            await self.handle_authentication_failure(error_msg)
            return False
        finally:
            # Always close the auth manager's HTTP session
            await self.auth_manager.close()


async def validate_startup_authentication(auth_manager: AuthenticationManager) -> bool:
    """
    Convenience function for startup authentication validation.
    
    Args:
        auth_manager: AuthenticationManager instance
        
    Returns:
        bool: True if authentication is valid, False otherwise
    """
    validator = StartupAuthValidator(auth_manager)
    return await validator.perform_startup_validation()