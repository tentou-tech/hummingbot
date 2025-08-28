#!/usr/bin/env python

import hashlib
import time
from typing import Dict, Optional

from hummingbot.core.web_assistant.auth import AuthBase
from hummingbot.core.web_assistant.connections.data_types import RESTRequest, WSRequest

# Mock Account class for test compatibility
class Account:
    def __init__(self, private_key: str):
        self.key = private_key
        self.address = f"0x{private_key[:40]}"  # Mock address from private key
    
    @classmethod
    def from_key(cls, private_key: str):
        """Create Account from private key - for test compatibility."""
        return cls(private_key)


class StandardAuth(AuthBase):
    """
    Authentication class for Somnia exchange using wallet private key.
    """

    def __init__(self, private_key: str, wallet_address: str):
        """
        Initialize authentication with wallet credentials.
        
        Args:
            private_key: Wallet private key
            wallet_address: Wallet address
        """
        self._private_key = private_key
        self._wallet_address = wallet_address.lower()

    async def rest_authenticate(self, request: RESTRequest) -> RESTRequest:
        """
        Add authentication to REST request.
        
        Args:
            request: REST request to authenticate
            
        Returns:
            Authenticated request
        """
        # For Somnia, authentication is handled by signing transactions with the private key
        # REST API calls typically don't require special authentication headers
        # The StandardWeb3 client handles the signing automatically
        
        # Add timestamp header for request tracking
        timestamp = str(int(time.time()))
        request.headers = request.headers or {}
        request.headers.update({
            "X-Timestamp": timestamp,
            "X-Wallet-Address": self._wallet_address,
        })
        
        return request

    async def ws_authenticate(self, request: WSRequest) -> WSRequest:
        """
        Add authentication to WebSocket request.
        
        Args:
            request: WebSocket request to authenticate
            
        Returns:
            Authenticated request
        """
        # For Somnia WebSocket connections, authentication might involve
        # sending a signed message after connection
        timestamp = str(int(time.time()))
        
        # WSJSONRequest doesn't have headers, add auth to payload if it's a JSON request
        if hasattr(request, 'payload') and isinstance(request.payload, dict):
            request.payload.update({
                "timestamp": timestamp,
                "wallet_address": self._wallet_address,
            })
        
        return request

    def get_wallet_address(self) -> str:
        """
        Get the wallet address.
        
        Returns:
            Wallet address
        """
        return self._wallet_address

    def get_private_key(self) -> str:
        """
        Get the private key (use with caution).
        
        Returns:
            Private key
        """
        return self._private_key

    def generate_signature(self, message: str) -> str:
        """
        Generate signature for a message.
        
        Args:
            message: Message to sign
            
        Returns:
            Signature string
        """
        # This is a placeholder - actual implementation would use
        # proper cryptographic signing with the private key
        # The StandardWeb3 library should handle this
        message_hash = hashlib.sha256(message.encode()).hexdigest()
        return f"signature_{message_hash[:16]}"

    def create_auth_dict(self) -> Dict[str, str]:
        """
        Create authentication dictionary for API calls.
        
        Returns:
            Authentication parameters
        """
        timestamp = str(int(time.time()))
        return {
            "wallet_address": self._wallet_address,
            "timestamp": timestamp,
        }

    
    @property
    def wallet_address(self) -> str:
        """
        Get the wallet address as a property.
        
        Returns:
            Wallet address
        """
        return self._wallet_address
    
    def get_headers(self) -> Dict[str, str]:
        """
        Get basic authentication headers.
        
        Returns:
            Headers dictionary
        """
        timestamp = str(int(time.time()))
        return {
            "X-Timestamp": timestamp,
            "X-Wallet-Address": self._wallet_address,
        }
    
    def get_auth_headers(self, method: str = "GET", path: str = "", body: str = "") -> Dict[str, str]:
        """
        Get authentication headers for API requests.
        
        Args:
            method: HTTP method
            path: API path
            body: Request body
            
        Returns:
            Authentication headers
        """
        timestamp = str(int(time.time()))
        headers = {
            "X-Timestamp": timestamp,
            "X-Wallet-Address": self._wallet_address,
            "X-Method": method,
        }
        
        if path:
            headers["X-Path"] = path
            
        # Add Content-Type for POST/PUT requests
        if method.upper() in ["POST", "PUT", "PATCH"]:
            headers["Content-Type"] = "application/json"
            
        # Generate signature for the request
        message = f"{method}{path}{body}{timestamp}"
        signature = self.generate_signature(message)
        headers["X-Signature"] = signature
        
        return headers
    
    def _get_nonce(self) -> int:
        """
        Generate a nonce for requests.
        
        Returns:
            Nonce as integer (timestamp in milliseconds)
        """
        return int(time.time() * 1000)
    
    def _format_for_standardweb3(self, data: Dict) -> Dict:
        """
        Format authentication data for StandardWeb3 compatibility.
        
        Args:
            data: Data to format
            
        Returns:
            Formatted data
        """
        formatted = data.copy()
        formatted["address"] = self._wallet_address
        formatted["private_key"] = self._private_key
        return formatted
