"""
Content filtering implementation.

This module handles input and output content filtering
to prevent inappropriate content from being stored or generated.
"""

import re
import logging
from typing import Optional, Set, List
from pathlib import Path


class ContentFilter:
    """
    Content filtering system with configurable blocked words and text normalization.
    
    Provides both input filtering (for incoming chat messages) and output filtering
    (for bot-generated messages) with fail-safe blocking behavior.
    """
    
    def __init__(self, blocked_words_file: str = "blocked_words.txt"):
        """
        Initialize the content filter.
        
        Args:
            blocked_words_file: Path to the blocked words configuration file
        """
        self.blocked_words_file = blocked_words_file
        self.blocked_words: Set[str] = set()
        self.blocked_patterns: List[re.Pattern] = []
        self.logger = logging.getLogger(__name__)
        
        # Load blocked words on initialization
        self.load_blocked_words(blocked_words_file)
    
    def load_blocked_words(self, file_path: str) -> None:
        """
        Load blocked words from configuration file.
        
        Args:
            file_path: Path to the blocked words file
        """
        try:
            path = Path(file_path)
            if not path.exists():
                self.logger.warning(f"Blocked words file not found: {file_path}")
                return
            
            self.blocked_words.clear()
            self.blocked_patterns.clear()
            
            with open(path, 'r', encoding='utf-8') as f:
                for line_num, line in enumerate(f, 1):
                    line = line.strip()
                    
                    # Skip empty lines and comments
                    if not line or line.startswith('#'):
                        continue
                    
                    try:
                        # Handle both single words and phrases
                        original_lower = line.lower()
                        normalized_word = self.normalize_text(original_lower)
                        
                        if normalized_word:
                            self.blocked_words.add(normalized_word)
                            
                            # Create regex pattern for the original phrase (preserves spaces)
                            # and the normalized version (handles evasion)
                            escaped_original = re.escape(original_lower)
                            escaped_normalized = re.escape(normalized_word)
                            
                            # Pattern for original phrase with word boundaries
                            if ' ' in original_lower:
                                # For phrases, use lookahead/lookbehind for word boundaries
                                pattern1 = re.compile(rf'(?<!\w){escaped_original}(?!\w)', re.IGNORECASE)
                            else:
                                # For single words, use standard word boundaries
                                pattern1 = re.compile(rf'\b{escaped_original}\b', re.IGNORECASE)
                            
                            self.blocked_patterns.append(pattern1)
                            
                            # Add pattern for normalized version if different
                            if normalized_word != original_lower:
                                if ' ' in normalized_word:
                                    pattern2 = re.compile(rf'(?<!\w){escaped_normalized}(?!\w)', re.IGNORECASE)
                                else:
                                    pattern2 = re.compile(rf'\b{escaped_normalized}\b', re.IGNORECASE)
                                self.blocked_patterns.append(pattern2)
                            
                    except Exception as e:
                        self.logger.warning(f"Error processing line {line_num} in {file_path}: {e}")
            
            self.logger.info(f"Loaded {len(self.blocked_words)} blocked words from {file_path}")
            
        except Exception as e:
            self.logger.error(f"Failed to load blocked words from {file_path}: {e}")
            # Fail-safe: if we can't load the filter, we should be more restrictive
    
    def normalize_text(self, text: str) -> str:
        """
        Normalize text to handle evasion attempts.
        
        This handles:
        - Leetspeak substitutions (3 -> e, 4 -> a, etc.)
        - Extra spacing and punctuation
        - Unicode variations
        - Case normalization
        
        Args:
            text: Text to normalize
            
        Returns:
            Normalized text
        """
        if not text:
            return ""
        
        # Convert to lowercase
        normalized = text.lower()
        
        # Remove extra whitespace and punctuation between characters
        # This catches attempts like "s p a m" or "s.p.a.m"
        normalized = re.sub(r'[\s\.\-_\*\+\=\|\\\/<>]+', '', normalized)
        
        # Handle common leetspeak substitutions
        # Only substitute when it's clearly leetspeak (surrounded by letters or at word boundaries)
        leetspeak_map = {
            '0': 'o',
            '1': 'i', 
            '3': 'e',
            '4': 'a',
            '5': 's',
            '7': 't',
            '8': 'b',
            '@': 'a',
            '$': 's',
            '|': 'l',
        }
        
        for leet, normal in leetspeak_map.items():
            normalized = normalized.replace(leet, normal)
        
        # Remove any remaining non-alphabetic characters
        normalized = re.sub(r'[^a-z]', '', normalized)
        
        return normalized
    
    def filter_input(self, message: str) -> Optional[str]:
        """
        Filter incoming chat message content.
        
        Args:
            message: The incoming chat message to filter
            
        Returns:
            The original message if clean, None if blocked
        """
        if not message:
            return message
        
        try:
            # Normalize the message for checking
            normalized = self.normalize_text(message)
            
            # Check against blocked patterns
            for pattern in self.blocked_patterns:
                if pattern.search(message) or pattern.search(normalized):
                    self.logger.warning(
                        "Input message blocked by content filter",
                        extra={
                            "original_message": message,
                            "normalized_message": normalized,
                            "filter_reason": "blocked_word_match"
                        }
                    )
                    return None
            
            # Additional checks for common evasion patterns
            if self._check_evasion_patterns(message, normalized):
                self.logger.warning(
                    "Input message blocked by evasion pattern detection",
                    extra={
                        "original_message": message,
                        "normalized_message": normalized,
                        "filter_reason": "evasion_pattern"
                    }
                )
                return None
            
            return message
            
        except Exception as e:
            self.logger.error(f"Error in input filtering: {e}")
            # Fail-safe: if filtering fails, block the message
            return None
    
    def filter_output(self, message: str) -> Optional[str]:
        """
        Filter bot-generated message content.
        
        Args:
            message: The bot-generated message to filter
            
        Returns:
            The original message if clean, None if blocked
        """
        if not message:
            return message
        
        try:
            # Normalize the message for checking
            normalized = self.normalize_text(message)
            
            # Check against blocked patterns
            for pattern in self.blocked_patterns:
                if pattern.search(message) or pattern.search(normalized):
                    self.logger.warning(
                        "Output message blocked by content filter",
                        extra={
                            "generated_message": message,
                            "normalized_message": normalized,
                            "filter_reason": "blocked_word_match"
                        }
                    )
                    return None
            
            # Additional checks for output-specific concerns
            if self._check_output_specific_issues(message, normalized):
                self.logger.warning(
                    "Output message blocked by output-specific filter",
                    extra={
                        "generated_message": message,
                        "normalized_message": normalized,
                        "filter_reason": "output_specific_issue"
                    }
                )
                return None
            
            return message
            
        except Exception as e:
            self.logger.error(f"Error in output filtering: {e}")
            # Fail-safe: if filtering fails, block the message
            return None
    
    def is_message_clean(self, message: str) -> bool:
        """
        Check if a message is clean without filtering it.
        
        Args:
            message: Message to check
            
        Returns:
            True if message is clean, False if it should be blocked
        """
        return self.filter_input(message) is not None
    
    def _check_evasion_patterns(self, original: str, normalized: str) -> bool:
        """
        Check for common evasion patterns that might bypass word matching.
        
        Args:
            original: Original message text
            normalized: Normalized message text
            
        Returns:
            True if evasion patterns detected, False otherwise
        """
        # Note: Removed repetitive content blocking - leave that to moderator discretion
        # Twitch chat culture includes things like "HAHAHAHAHA" and "nooooo" which are normal
        
        # Check for alternating case patterns that might be evasion attempts (e.g., "SpAm")
        # Only flag if it's very obvious evasion (most of the message alternates)
        alternating_case = sum(1 for i in range(len(original)-1) 
                             if original[i].islower() != original[i+1].islower())
        if len(original) > 6 and alternating_case > len(original) * 0.8:  # 80% alternating and longer messages
            return True
        
        # Check for excessive punctuation or symbols that might be evasion
        # Allow normal punctuation but block messages that are mostly symbols
        symbol_ratio = len(re.findall(r'[^\w\s]', original)) / max(len(original), 1)
        if symbol_ratio > 0.6:  # More than 60% symbols (very restrictive)
            return True
        
        return False
    
    def _check_output_specific_issues(self, original: str, normalized: str) -> bool:
        """
        Check for issues specific to bot-generated output.
        
        Args:
            original: Original message text
            normalized: Normalized message text
            
        Returns:
            True if output-specific issues detected, False otherwise
        """
        # Check for potential prompt injection attempts in output
        injection_patterns = [
            r'ignore\s+previous\s+instructions',
            r'system\s*:',
            r'assistant\s*:',
            r'user\s*:',
            r'prompt\s*:',
            r'<\|.*?\|>',  # Special tokens
        ]
        
        for pattern in injection_patterns:
            if re.search(pattern, original, re.IGNORECASE):
                return True
        
        # Check for attempts to impersonate other users
        if re.search(r'^\s*@\w+\s*:', original) or re.search(r'^\s*\w+\s*:', original):
            return True
        
        return False
    
    def reload_blocked_words(self) -> None:
        """
        Reload blocked words from the configuration file.
        
        Useful for updating filters without restarting the bot.
        """
        self.logger.info("Reloading blocked words configuration")
        self.load_blocked_words(self.blocked_words_file)
    
    def get_stats(self) -> dict:
        """
        Get statistics about the content filter.
        
        Returns:
            Dictionary with filter statistics
        """
        return {
            "blocked_words_count": len(self.blocked_words),
            "blocked_patterns_count": len(self.blocked_patterns),
            "config_file": self.blocked_words_file
        }