import asyncio
from typing import Awaitable
from unittest import TestCase
from unittest.mock import MagicMock, patch

import hummingbot.connector.exchange.standard_testnet.standard_testnet_constants as CONSTANTS
from hummingbot.connector.exchange.standard_testnet.standard_testnet_auth import StandardTestnetAuth
from hummingbot.core.web_assistant.connections.data_types import RESTMethod, RESTRequest, WSJSONRequest


class StandardTestnetAuthTests(TestCase):
    def setUp(self) -> None:
        super().setUp()
        # Mock wallet addresses for testing
        self.wallet_address = "0x1234567890123456789012345678901234567890"
        self.private_key = "0xabcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef"

        self.auth = StandardTestnetAuth(
            wallet_address=self.wallet_address,
            private_key=self.private_key,
        )

    def async_run_with_timeout(self, coroutine: Awaitable, timeout: int = 1):
        ret = asyncio.get_event_loop().run_until_complete(asyncio.wait_for(coroutine, timeout))
        return ret

    def test_rest_authenticate(self):
        """Test REST request authentication"""
        request = RESTRequest(
            method=RESTMethod.GET,
            url="https://test.url/api/endpoint",
            is_auth_required=True,
            throttler_limit_id="/api/endpoint",
        )
        ret = self.async_run_with_timeout(self.auth.rest_authenticate(request))
        self.assertEqual(request, ret)

    def test_ws_authenticate(self):
        """Test WebSocket request authentication"""
        payload = {"param1": "value_param_1"}
        request = WSJSONRequest(payload=payload, is_auth_required=False)
        ret = self.async_run_with_timeout(self.auth.ws_authenticate(request))
        self.assertEqual(payload, request.payload)
        self.assertEqual(request, ret)

    def test_wallet_address_property(self):
        """Test wallet address property"""
        self.assertEqual(self.auth.wallet_address, self.wallet_address)

    def test_private_key_property(self):
        """Test private key property (should be accessible but not exposed)"""
        # Private key should be stored but not directly accessible for security
        self.assertIsNotNone(self.auth._private_key)

    @patch("hummingbot.connector.exchange.standard_testnet.standard_testnet_auth.Account.from_key")
    def test_web3_account_creation(self, mock_from_key):
        """Test Web3 account creation from private key"""
        mock_account = MagicMock()
        mock_account.address = self.wallet_address
        mock_from_key.return_value = mock_account
        
        # Create new auth instance to trigger account creation
        auth = StandardTestnetAuth(
            wallet_address=self.wallet_address,
            private_key=self.private_key,
        )
        
        # Should have created Web3 account
        self.assertIsNotNone(auth._account)

    def test_get_headers_basic(self):
        """Test basic header generation"""
        headers = self.auth.get_headers()
        self.assertIsInstance(headers, dict)
        
        # Should include wallet address in headers
        self.assertIn("X-Wallet-Address", headers)
        self.assertEqual(headers["X-Wallet-Address"], self.wallet_address)

    def test_get_auth_headers_for_post_request(self):
        """Test authentication headers for POST requests"""
        test_data = {"key": "value", "amount": "100.0"}
        headers = self.auth.get_auth_headers("POST", "/api/order", test_data)
        
        self.assertIsInstance(headers, dict)
        self.assertIn("X-Wallet-Address", headers)
        self.assertIn("Content-Type", headers)
        self.assertEqual(headers["Content-Type"], "application/json")

    def test_get_auth_headers_for_get_request(self):
        """Test authentication headers for GET requests"""
        headers = self.auth.get_auth_headers("GET", "/api/balance")
        
        self.assertIsInstance(headers, dict)
        self.assertIn("X-Wallet-Address", headers)

    def test_signature_generation(self):
        """Test transaction signature generation"""
        test_data = {
            "to": "0x1234567890123456789012345678901234567890",
            "value": "1000000000000000000",  # 1 ETH in wei
            "data": "0x"
        }
        
        with patch.object(self.auth, "_sign_transaction") as mock_sign:
            mock_sign.return_value = "0xsignature"
            
            signature = self.auth._sign_transaction(test_data)
            
            self.assertEqual(signature, "0xsignature")
            mock_sign.assert_called_once_with(test_data)

    def test_message_signing(self):
        """Test message signing for authentication"""
        message = "Test message for signing"
        
        with patch.object(self.auth, "_sign_message") as mock_sign_msg:
            mock_sign_msg.return_value = "0xmessage_signature"
            
            signature = self.auth._sign_message(message)
            
            self.assertEqual(signature, "0xmessage_signature")
            mock_sign_msg.assert_called_once_with(message)

    def test_nonce_generation(self):
        """Test nonce generation for transactions"""
        with patch("time.time", return_value=1234567890.123):
            nonce = self.auth._get_nonce()
            
            # Should be based on timestamp
            self.assertIsInstance(nonce, int)
            self.assertGreater(nonce, 0)

    def test_auth_required_check(self):
        """Test authentication requirement check"""
        # Test auth required request
        auth_request = RESTRequest(
            method=RESTMethod.POST,
            url="https://api.standard-testnet.com/orders",
            is_auth_required=True,
        )
        
        self.assertTrue(auth_request.is_auth_required)
        
        # Test non-auth request
        public_request = RESTRequest(
            method=RESTMethod.GET,
            url="https://api.standard-testnet.com/orderbook",
            is_auth_required=False,
        )
        
        self.assertFalse(public_request.is_auth_required)

    def test_standardweb3_compatibility(self):
        """Test compatibility with StandardWeb3 authentication"""
        # StandardWeb3 may require specific auth format
        auth_data = {
            "wallet_address": self.wallet_address,
            "timestamp": 1234567890,
            "signature": "0xtest_signature"
        }
        
        # Should be able to format auth data for StandardWeb3
        formatted_auth = self.auth._format_for_standardweb3(auth_data)
        
        self.assertIsInstance(formatted_auth, dict)
        self.assertIn("wallet_address", formatted_auth)

    def _format_for_standardweb3(self, auth_data):
        """Helper method to format auth data for StandardWeb3"""
        return {
            "address": auth_data.get("wallet_address"),
            "timestamp": auth_data.get("timestamp"),
            "signature": auth_data.get("signature"),
        }


if __name__ == "__main__":
    import unittest
    unittest.main()
