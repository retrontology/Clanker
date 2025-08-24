"""
Token management and storage.

This module handles secure storage and management of authentication tokens
with encryption for sensitive data and automatic refresh logic.
"""

import base64
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from cryptography.fernet import Fernet
import os

from ..database.models import AuthToken

logger = logging.getLogger(__name__)


class TokenManager:
    """Manages secure storage and encryption of authentication tokens."""
    
    def __init__(self, encryption_key: Optional[str] = None):
        """
        Initialize TokenManager with encryption.
        
        Args:
            encryption_key: Base64-encoded encryption key. If None, generates new key.
        """
        if encryption_key:
            self.encryption_key = encryption_key.encode()
        else:
            # Generate a new key if none provided
            self.encryption_key = Fernet.generate_key()
            logger.warning("Generated new encryption key. Store this securely: %s", 
                         base64.b64encode(self.encryption_key).decode())
        
        self.cipher = Fernet(self.encryption_key)
    
    def encrypt_token(self, token: str) -> str:
        """
        Encrypt a token for secure storage.
        
        Args:
            token: Plain text token
            
        Returns:
            str: Encrypted token as base64 string
        """
        try:
            encrypted_bytes = self.cipher.encrypt(token.encode())
            return base64.b64encode(encrypted_bytes).decode()
        except Exception as e:
            logger.error(f"Failed to encrypt token: {e}")
            raise
    
    def decrypt_token(self, encrypted_token: str) -> str:
        """
        Decrypt a token from storage.
        
        Args:
            encrypted_token: Base64-encoded encrypted token
            
        Returns:
            str: Decrypted plain text token
        """
        try:
            encrypted_bytes = base64.b64decode(encrypted_token.encode())
            decrypted_bytes = self.cipher.decrypt(encrypted_bytes)
            return decrypted_bytes.decode()
        except Exception as e:
            logger.error(f"Failed to decrypt token: {e}")
            raise
    
    def is_token_expired(self, expires_at: Optional[datetime]) -> bool:
        """
        Check if a token is expired.
        
        Args:
            expires_at: Token expiration datetime
            
        Returns:
            bool: True if expired or no expiration date, False otherwise
        """
        if not expires_at:
            return True
        
        # Add 5 minute buffer to avoid edge cases
        buffer_time = timedelta(minutes=5)
        return datetime.now() >= (expires_at - buffer_time)
    
    def create_auth_token(self, access_token: str, refresh_token: Optional[str] = None,
                         expires_in: Optional[int] = None, bot_username: Optional[str] = None) -> AuthToken:
        """
        Create an AuthToken object with encrypted tokens.
        
        Args:
            access_token: Plain text access token
            refresh_token: Plain text refresh token (optional)
            expires_in: Token lifetime in seconds (optional)
            bot_username: Bot username from OAuth response (optional)
            
        Returns:
            AuthToken: Token object with encrypted data
        """
        try:
            # Encrypt the tokens
            encrypted_access = self.encrypt_token(access_token)
            encrypted_refresh = self.encrypt_token(refresh_token) if refresh_token else None
            
            # Calculate expiration time
            expires_at = None
            if expires_in:
                expires_at = datetime.now() + timedelta(seconds=expires_in)
            
            return AuthToken(
                id=None,
                access_token=encrypted_access,
                refresh_token=encrypted_refresh,
                expires_at=expires_at,
                bot_username=bot_username,
                created_at=datetime.now()
            )
            
        except Exception as e:
            logger.error(f"Failed to create auth token: {e}")
            raise
    
    def get_decrypted_access_token(self, auth_token: AuthToken) -> str:
        """
        Get decrypted access token from AuthToken object.
        
        Args:
            auth_token: AuthToken object with encrypted data
            
        Returns:
            str: Decrypted access token
        """
        return self.decrypt_token(auth_token.access_token)
    
    def get_decrypted_refresh_token(self, auth_token: AuthToken) -> Optional[str]:
        """
        Get decrypted refresh token from AuthToken object.
        
        Args:
            auth_token: AuthToken object with encrypted data
            
        Returns:
            Optional[str]: Decrypted refresh token or None
        """
        if not auth_token.refresh_token:
            return None
        return self.decrypt_token(auth_token.refresh_token)