"""
OAuth handling for Twitch authentication.

This module handles OAuth flow, token validation, and automatic
token refresh for Twitch API access.
"""

import aiohttp
import logging
from typing import Optional, Dict, Any, Tuple
from datetime import datetime
import asyncio

logger = logging.getLogger(__name__)


class TwitchOAuthClient:
    """Handles Twitch OAuth operations and token management."""
    
    def __init__(self, client_id: str, client_secret: str):
        """
        Initialize TwitchOAuthClient.
        
        Args:
            client_id: Twitch application client ID
            client_secret: Twitch application client secret
        """
        self.client_id = client_id
        self.client_secret = client_secret
        self.base_url = "https://id.twitch.tv/oauth2"
        self.api_base_url = "https://api.twitch.tv/helix"
        
        # HTTP session for connection reuse
        self._session: Optional[aiohttp.ClientSession] = None
    
    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create HTTP session."""
        if not self._session or self._session.closed:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=30)
            )
        return self._session
    
    async def close(self):
        """Close HTTP session."""
        if self._session and not self._session.closed:
            await self._session.close()
    
    async def validate_token(self, access_token: str) -> Tuple[bool, Optional[Dict[str, Any]]]:
        """
        Validate an access token with Twitch.
        
        Args:
            access_token: Access token to validate
            
        Returns:
            Tuple[bool, Optional[Dict]]: (is_valid, token_info)
        """
        try:
            session = await self._get_session()
            
            headers = {
                'Authorization': f'OAuth {access_token}'
            }
            
            async with session.get(f"{self.base_url}/validate", headers=headers) as response:
                if response.status == 200:
                    token_info = await response.json()
                    logger.info("Token validation successful")
                    return True, token_info
                elif response.status == 401:
                    logger.warning("Token validation failed: token is invalid")
                    return False, None
                else:
                    logger.error(f"Token validation failed with status {response.status}")
                    return False, None
                    
        except Exception as e:
            logger.error(f"Token validation error: {e}")
            return False, None
    
    async def refresh_token(self, refresh_token: str) -> Optional[Dict[str, Any]]:
        """
        Refresh an access token using refresh token.
        
        Args:
            refresh_token: Refresh token
            
        Returns:
            Optional[Dict]: New token data or None if failed
        """
        try:
            session = await self._get_session()
            
            data = {
                'grant_type': 'refresh_token',
                'refresh_token': refresh_token,
                'client_id': self.client_id,
                'client_secret': self.client_secret
            }
            
            async with session.post(f"{self.base_url}/token", data=data) as response:
                if response.status == 200:
                    token_data = await response.json()
                    logger.info("Token refresh successful")
                    return token_data
                else:
                    error_text = await response.text()
                    logger.error(f"Token refresh failed with status {response.status}: {error_text}")
                    return None
                    
        except Exception as e:
            logger.error(f"Token refresh error: {e}")
            return None
    
    async def get_user_info(self, access_token: str) -> Optional[Dict[str, Any]]:
        """
        Get user information from Twitch API.
        
        Args:
            access_token: Valid access token
            
        Returns:
            Optional[Dict]: User information or None if failed
        """
        try:
            session = await self._get_session()
            
            headers = {
                'Authorization': f'Bearer {access_token}',
                'Client-Id': self.client_id
            }
            
            async with session.get(f"{self.api_base_url}/users", headers=headers) as response:
                if response.status == 200:
                    user_data = await response.json()
                    if user_data.get('data'):
                        logger.info("User info retrieved successfully")
                        return user_data['data'][0]  # Return first user (should be the authenticated user)
                    else:
                        logger.error("No user data in response")
                        return None
                else:
                    error_text = await response.text()
                    logger.error(f"Get user info failed with status {response.status}: {error_text}")
                    return None
                    
        except Exception as e:
            logger.error(f"Get user info error: {e}")
            return None
    
    async def revoke_token(self, access_token: str) -> bool:
        """
        Revoke an access token.
        
        Args:
            access_token: Access token to revoke
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            session = await self._get_session()
            
            data = {
                'client_id': self.client_id,
                'token': access_token
            }
            
            async with session.post(f"{self.base_url}/revoke", data=data) as response:
                if response.status == 200:
                    logger.info("Token revoked successfully")
                    return True
                else:
                    error_text = await response.text()
                    logger.error(f"Token revocation failed with status {response.status}: {error_text}")
                    return False
                    
        except Exception as e:
            logger.error(f"Token revocation error: {e}")
            return False
    
    def get_authorization_url(self, scopes: list, redirect_uri: str, state: Optional[str] = None) -> str:
        """
        Generate authorization URL for OAuth flow.
        
        Args:
            scopes: List of requested scopes
            redirect_uri: Redirect URI after authorization
            state: Optional state parameter for CSRF protection
            
        Returns:
            str: Authorization URL
        """
        params = {
            'client_id': self.client_id,
            'redirect_uri': redirect_uri,
            'response_type': 'code',
            'scope': ' '.join(scopes)
        }
        
        if state:
            params['state'] = state
        
        query_string = '&'.join([f"{k}={v}" for k, v in params.items()])
        return f"{self.base_url}/authorize?{query_string}"
    
    async def exchange_code_for_token(self, code: str, redirect_uri: str) -> Optional[Dict[str, Any]]:
        """
        Exchange authorization code for access token.
        
        Args:
            code: Authorization code from OAuth callback
            redirect_uri: Redirect URI used in authorization
            
        Returns:
            Optional[Dict]: Token data or None if failed
        """
        try:
            session = await self._get_session()
            
            data = {
                'client_id': self.client_id,
                'client_secret': self.client_secret,
                'code': code,
                'grant_type': 'authorization_code',
                'redirect_uri': redirect_uri
            }
            
            async with session.post(f"{self.base_url}/token", data=data) as response:
                if response.status == 200:
                    token_data = await response.json()
                    logger.info("Authorization code exchange successful")
                    return token_data
                else:
                    error_text = await response.text()
                    logger.error(f"Code exchange failed with status {response.status}: {error_text}")
                    return None
                    
        except Exception as e:
            logger.error(f"Code exchange error: {e}")
            return None