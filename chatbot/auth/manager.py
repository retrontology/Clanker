"""
Authentication Manager for comprehensive OAuth token management.

This module provides the main AuthenticationManager class that coordinates
token storage, validation, refresh, and username detection.
"""

import logging
import asyncio
from typing import Optional, Dict, Any
from datetime import datetime

from .oauth import TwitchOAuthClient
from .tokens import TokenManager
from ..database.operations import AuthTokenManager
from ..database.models import AuthToken

logger = logging.getLogger(__name__)


class AuthenticationManager:
    """
    Main authentication manager that coordinates OAuth operations,
    token storage, and automatic refresh logic.
    """
    
    def __init__(self, client_id: str, client_secret: str, auth_token_manager: AuthTokenManager,
                 encryption_key: Optional[str] = None):
        """
        Initialize AuthenticationManager.
        
        Args:
            client_id: Twitch application client ID
            client_secret: Twitch application client secret
            auth_token_manager: Database token manager
            encryption_key: Optional encryption key for token storage
        """
        self.oauth_client = TwitchOAuthClient(client_id, client_secret)
        self.token_manager = TokenManager(encryption_key)
        self.auth_token_manager = auth_token_manager
        
        self._current_token: Optional[AuthToken] = None
        self._bot_username: Optional[str] = None
        self._retry_count = 0
        self._max_retries = 3
    
    async def close(self):
        """Close HTTP sessions and cleanup resources."""
        await self.oauth_client.close()
    
    async def store_initial_tokens(self, access_token: str, refresh_token: Optional[str] = None,
                                 expires_in: Optional[int] = None) -> bool:
        """
        Store initial authentication tokens and detect bot username.
        
        Args:
            access_token: Plain text access token
            refresh_token: Plain text refresh token (optional)
            expires_in: Token lifetime in seconds (optional)
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            # Validate token and get user info
            is_valid, token_info = await self.oauth_client.validate_token(access_token)
            if not is_valid:
                logger.error("Invalid access token provided")
                return False
            
            # Get username from token validation or user API
            bot_username = None
            if token_info and 'login' in token_info:
                bot_username = token_info['login']
            else:
                # Fallback to user API
                user_info = await self.oauth_client.get_user_info(access_token)
                if user_info and 'login' in user_info:
                    bot_username = user_info['login']
            
            if not bot_username:
                logger.error("Could not detect bot username from OAuth response")
                return False
            
            # Create encrypted token object
            auth_token = self.token_manager.create_auth_token(
                access_token=access_token,
                refresh_token=refresh_token,
                expires_in=expires_in,
                bot_username=bot_username
            )
            
            # Store in database
            if await self.auth_token_manager.store_auth_tokens(auth_token):
                self._current_token = auth_token
                self._bot_username = bot_username
                logger.info(f"Authentication tokens stored successfully for bot: {bot_username}")
                return True
            else:
                logger.error("Failed to store authentication tokens in database")
                return False
                
        except Exception as e:
            logger.error(f"Failed to store initial tokens: {e}")
            return False
    
    async def load_stored_tokens(self) -> bool:
        """
        Load stored tokens from database and validate them.
        
        Returns:
            bool: True if valid tokens loaded, False otherwise
        """
        try:
            # Load from database
            stored_token = await self.auth_token_manager.get_auth_tokens()
            if not stored_token:
                logger.info("No stored authentication tokens found")
                return False
            
            # Decrypt and validate
            access_token = self.token_manager.get_decrypted_access_token(stored_token)
            
            # Check if token is expired
            if self.token_manager.is_token_expired(stored_token.expires_at):
                logger.info("Stored token is expired, attempting refresh")
                return await self._refresh_stored_token(stored_token)
            
            # Validate with Twitch
            is_valid, token_info = await self.oauth_client.validate_token(access_token)
            if is_valid:
                self._current_token = stored_token
                self._bot_username = stored_token.bot_username
                logger.info(f"Valid authentication tokens loaded for bot: {self._bot_username}")
                return True
            else:
                logger.info("Stored token is invalid, attempting refresh")
                return await self._refresh_stored_token(stored_token)
                
        except Exception as e:
            logger.error(f"Failed to load stored tokens: {e}")
            return False
    
    async def _refresh_stored_token(self, stored_token: AuthToken) -> bool:
        """
        Refresh stored token using refresh token.
        
        Args:
            stored_token: Current stored token
            
        Returns:
            bool: True if refresh successful, False otherwise
        """
        try:
            if not stored_token.refresh_token:
                logger.error("No refresh token available for token refresh")
                return False
            
            # Decrypt refresh token
            refresh_token = self.token_manager.get_decrypted_refresh_token(stored_token)
            if not refresh_token:
                logger.error("Could not decrypt refresh token")
                return False
            
            # Attempt refresh with retry logic
            new_token_data = await self._refresh_with_retry(refresh_token)
            if not new_token_data:
                logger.error("Token refresh failed after retries")
                return False
            
            # Create new encrypted token
            new_auth_token = self.token_manager.create_auth_token(
                access_token=new_token_data['access_token'],
                refresh_token=new_token_data.get('refresh_token', refresh_token),
                expires_in=new_token_data.get('expires_in'),
                bot_username=stored_token.bot_username
            )
            new_auth_token.id = stored_token.id  # Keep same ID for update
            
            # Update in database
            if await self.auth_token_manager.update_auth_tokens(new_auth_token):
                self._current_token = new_auth_token
                self._bot_username = stored_token.bot_username
                logger.info("Authentication token refreshed successfully")
                return True
            else:
                logger.error("Failed to update refreshed tokens in database")
                return False
                
        except Exception as e:
            logger.error(f"Failed to refresh stored token: {e}")
            return False
    
    async def _refresh_with_retry(self, refresh_token: str) -> Optional[Dict[str, Any]]:
        """
        Refresh token with exponential backoff retry logic.
        
        Args:
            refresh_token: Refresh token to use
            
        Returns:
            Optional[Dict]: New token data or None if failed
        """
        for attempt in range(self._max_retries):
            try:
                new_token_data = await self.oauth_client.refresh_token(refresh_token)
                if new_token_data:
                    self._retry_count = 0  # Reset on success
                    return new_token_data
                
                # Wait before retry
                if attempt < self._max_retries - 1:
                    delay = 2 ** attempt  # Exponential backoff: 1s, 2s, 4s
                    logger.warning(f"Token refresh attempt {attempt + 1} failed, retrying in {delay}s")
                    await asyncio.sleep(delay)
                    
            except Exception as e:
                logger.error(f"Token refresh attempt {attempt + 1} error: {e}")
                if attempt < self._max_retries - 1:
                    delay = 2 ** attempt
                    await asyncio.sleep(delay)
        
        return None
    
    async def ensure_valid_token(self) -> Optional[str]:
        """
        Ensure we have a valid access token, refreshing if necessary.
        
        Returns:
            Optional[str]: Valid access token or None if unavailable
        """
        try:
            if not self._current_token:
                # Try to load from database
                if not await self.load_stored_tokens():
                    logger.error("No valid authentication tokens available")
                    return None
            
            # Check if current token is expired
            if self.token_manager.is_token_expired(self._current_token.expires_at):
                logger.info("Current token is expired, attempting refresh")
                if not await self._refresh_stored_token(self._current_token):
                    logger.error("Failed to refresh expired token")
                    return None
            
            # Return decrypted access token
            return self.token_manager.get_decrypted_access_token(self._current_token)
            
        except Exception as e:
            logger.error(f"Failed to ensure valid token: {e}")
            return None
    
    async def validate_authentication(self) -> bool:
        """
        Validate current authentication status.
        
        Returns:
            bool: True if authentication is valid, False otherwise
        """
        try:
            access_token = await self.ensure_valid_token()
            if not access_token:
                return False
            
            # Validate with Twitch
            is_valid, _ = await self.oauth_client.validate_token(access_token)
            if is_valid:
                logger.info(f"Authentication validation successful for bot: {self._bot_username}")
                return True
            else:
                logger.error("Authentication validation failed")
                return False
                
        except Exception as e:
            logger.error(f"Authentication validation error: {e}")
            return False
    
    def get_bot_username(self) -> Optional[str]:
        """
        Get the authenticated bot's username.
        
        Returns:
            Optional[str]: Bot username or None if not authenticated
        """
        return self._bot_username
    
    async def revoke_tokens(self) -> bool:
        """
        Revoke current tokens and clear from database.
        
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            success = True
            
            # Revoke with Twitch if we have a current token
            if self._current_token:
                access_token = self.token_manager.get_decrypted_access_token(self._current_token)
                if not await self.oauth_client.revoke_token(access_token):
                    logger.warning("Failed to revoke token with Twitch")
                    success = False
            
            # Clear from database
            if not await self.auth_token_manager.delete_auth_tokens():
                logger.error("Failed to delete tokens from database")
                success = False
            
            # Clear local state
            self._current_token = None
            self._bot_username = None
            
            if success:
                logger.info("Authentication tokens revoked successfully")
            
            return success
            
        except Exception as e:
            logger.error(f"Failed to revoke tokens: {e}")
            return False
    
    async def get_authorization_url(self, redirect_uri: str, state: Optional[str] = None) -> str:
        """
        Get authorization URL for OAuth flow.
        
        Args:
            redirect_uri: Redirect URI after authorization
            state: Optional state parameter for CSRF protection
            
        Returns:
            str: Authorization URL
        """
        # Required scopes for Twitch chatbot
        scopes = ['chat:read', 'chat:edit']
        return self.oauth_client.get_authorization_url(scopes, redirect_uri, state)
    
    async def exchange_code_for_tokens(self, code: str, redirect_uri: str) -> bool:
        """
        Exchange authorization code for tokens and store them.
        
        Args:
            code: Authorization code from OAuth callback
            redirect_uri: Redirect URI used in authorization
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            # Exchange code for tokens
            token_data = await self.oauth_client.exchange_code_for_token(code, redirect_uri)
            if not token_data:
                logger.error("Failed to exchange authorization code for tokens")
                return False
            
            # Store the tokens
            return await self.store_initial_tokens(
                access_token=token_data['access_token'],
                refresh_token=token_data.get('refresh_token'),
                expires_in=token_data.get('expires_in')
            )
            
        except Exception as e:
            logger.error(f"Failed to exchange code for tokens: {e}")
            return False