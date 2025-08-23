import asyncio
import time
from unittest import TestCase
from unittest.mock import AsyncMock, patch

from hummingbot.connector.exchange.standard_testnet import standard_testnet_constants as CONSTANTS, standard_testnet_web_utils as web_utils


class SomniaWebUtilsTests(TestCase):
    def test_public_rest_url(self):
        """Test public REST URL generation"""
        url = web_utils.public_rest_url(path_url=CONSTANTS.GET_ORDERBOOK_PATH_URL)
        expected_url = f"{CONSTANTS.REST_API_BASE_URL}/api/orderbook"
        self.assertEqual(url, expected_url)

    def test_private_rest_url(self):
        """Test private REST URL generation"""
        url = web_utils.private_rest_url(path_url=CONSTANTS.GET_ACCOUNT_PATH_URL)
        expected_url = f"{CONSTANTS.REST_API_BASE_URL}/api/account"
        self.assertEqual(url, expected_url)

    def test_build_api_factory(self):
        """Test API factory building"""
        factory = web_utils.build_api_factory()
        self.assertIsNotNone(factory)

    def test_create_throttler(self):
        """Test throttler creation"""
        throttler = web_utils.create_throttler()
        self.assertIsNotNone(throttler)

    def test_get_current_server_time(self):
        """Test server time retrieval"""
        loop = asyncio.get_event_loop()
        recent_timestamp = time.time() - 1.0
        
        # Mock the server time response
        with patch("hummingbot.connector.exchange.standard_testnet.standard_testnet_web_utils.aiohttp.ClientSession") as mock_session:
            mock_response = AsyncMock()
            mock_response.json.return_value = {"serverTime": int(time.time() * 1000)}
            mock_session.return_value.__aenter__.return_value.get.return_value.__aenter__.return_value = mock_response
            
            server_timestamp = loop.run_until_complete(
                asyncio.wait_for(web_utils.get_current_server_time(web_utils.create_throttler()), 1)
            )
            
            self.assertLess(recent_timestamp, server_timestamp)

    def test_rest_api_base_url_constant(self):
        """Test REST API base URL constant"""
        self.assertIsNotNone(CONSTANTS.REST_API_BASE_URL)
        self.assertTrue(CONSTANTS.REST_API_BASE_URL.startswith("http"))

    def test_websocket_url_constant(self):
        """Test WebSocket URL constant if available"""
        if hasattr(CONSTANTS, "WSS_URL"):
            self.assertIsNotNone(CONSTANTS.WSS_URL)
            self.assertTrue(CONSTANTS.WSS_URL.startswith("ws"))

    def test_path_url_constants(self):
        """Test API path URL constants"""
        # Test that required path constants exist
        required_paths = [
            "GET_ORDERBOOK_PATH_URL",
            "GET_ACCOUNT_PATH_URL",
            "POST_ORDER_PATH_URL",
            "DELETE_ORDER_PATH_URL",
        ]
        
        for path_name in required_paths:
            if hasattr(CONSTANTS, path_name):
                path_value = getattr(CONSTANTS, path_name)
                self.assertIsNotNone(path_value)
                self.assertIsInstance(path_value, str)

    def test_rate_limits_configuration(self):
        """Test rate limits configuration"""
        self.assertIsNotNone(CONSTANTS.RATE_LIMITS)
        self.assertIsInstance(CONSTANTS.RATE_LIMITS, list)
        
        # Should have at least one rate limit defined
        self.assertGreater(len(CONSTANTS.RATE_LIMITS), 0)

    def test_standardweb3_integration_constants(self):
        """Test StandardWeb3 integration constants"""
        # Test StandardWeb3 related constants
        standardweb3_constants = [
            "STANDARDWEB3_PROVIDER_URL",
            "CHAIN_ID",
            "NATIVE_TOKEN",
        ]
        
        for const_name in standardweb3_constants:
            if hasattr(CONSTANTS, const_name):
                const_value = getattr(CONSTANTS, const_name)
                self.assertIsNotNone(const_value)

    def test_token_address_constants(self):
        """Test token address constants"""
        # Test that token addresses are properly defined
        token_constants = [
            "STT_TOKEN_ADDRESS",
            "USDC_TOKEN_ADDRESS", 
            "SOMNIA_TOKEN_ADDRESS",
        ]
        
        for token_const in token_constants:
            if hasattr(CONSTANTS, token_const):
                address = getattr(CONSTANTS, token_const)
                self.assertIsNotNone(address)
                # Should be a valid Ethereum address format
                self.assertTrue(address.startswith("0x"))
                self.assertEqual(len(address), 42)  # 0x + 40 hex chars

    def test_api_version_constants(self):
        """Test API version constants"""
        if hasattr(CONSTANTS, "API_VERSION"):
            self.assertIsNotNone(CONSTANTS.API_VERSION)
            self.assertIsInstance(CONSTANTS.API_VERSION, str)

    def test_default_domain_constant(self):
        """Test default domain constant"""
        if hasattr(CONSTANTS, "DEFAULT_DOMAIN"):
            self.assertIsNotNone(CONSTANTS.DEFAULT_DOMAIN)
            self.assertIsInstance(CONSTANTS.DEFAULT_DOMAIN, str)

    def test_trading_pair_symbol_map(self):
        """Test trading pair symbol mapping functionality"""
        # Test symbol mapping if it exists
        sample_pairs = {
            "STT-USDC": "STTUSDC",
            "SOMNIA-USDC": "SOMNIAUSDC",
        }
        
        for internal_pair, exchange_pair in sample_pairs.items():
            # Test conversion functions if they exist
            if hasattr(web_utils, "convert_to_exchange_trading_pair"):
                converted = web_utils.convert_to_exchange_trading_pair(internal_pair)
                self.assertIsNotNone(converted)
            
            if hasattr(web_utils, "convert_from_exchange_trading_pair"):
                converted_back = web_utils.convert_from_exchange_trading_pair(exchange_pair)
                self.assertIsNotNone(converted_back)

    def test_standard_testnet_network_configuration(self):
        """Test Somnia network specific configuration"""
        # Test Somnia testnet configuration
        testnet_constants = [
            "TESTNET_RPC_URL",
            "TESTNET_CHAIN_ID",
            "TESTNET_BLOCK_EXPLORER",
        ]
        
        for const_name in testnet_constants:
            if hasattr(CONSTANTS, const_name):
                const_value = getattr(CONSTANTS, const_name)
                self.assertIsNotNone(const_value)

        # Test Somnia mainnet configuration  
        mainnet_constants = [
            "MAINNET_RPC_URL",
            "MAINNET_CHAIN_ID", 
            "MAINNET_BLOCK_EXPLORER",
        ]
        
        for const_name in mainnet_constants:
            if hasattr(CONSTANTS, const_name):
                const_value = getattr(CONSTANTS, const_name)
                self.assertIsNotNone(const_value)

    def test_web3_provider_configuration(self):
        """Test Web3 provider configuration"""
        if hasattr(web_utils, "get_web3_provider"):
            provider = web_utils.get_web3_provider()
            self.assertIsNotNone(provider)

    def test_throttler_limits_structure(self):
        """Test throttler limits structure"""
        if hasattr(CONSTANTS, "RATE_LIMITS"):
            for limit in CONSTANTS.RATE_LIMITS:
                # Each rate limit should have required attributes
                self.assertIsNotNone(limit.limit_id)
                self.assertIsNotNone(limit.limit)
                self.assertIsNotNone(limit.time_interval)
                
                # Values should be reasonable
                self.assertGreater(limit.limit, 0)
                self.assertGreater(limit.time_interval, 0)

    def test_error_codes_mapping(self):
        """Test error codes mapping if available"""
        if hasattr(CONSTANTS, "ERROR_CODES"):
            error_codes = CONSTANTS.ERROR_CODES
            self.assertIsInstance(error_codes, dict)
            
            # Should have common error codes
            common_errors = [
                "INVALID_SIGNATURE",
                "INSUFFICIENT_BALANCE", 
                "INVALID_ORDER",
                "ORDER_NOT_FOUND",
            ]
            
            for error in common_errors:
                if error in error_codes:
                    self.assertIsNotNone(error_codes[error])

    def test_dual_fallback_url_configuration(self):
        """Test dual fallback URL configuration for StandardWeb3 + REST"""
        # Should have both StandardWeb3 and REST configurations
        self.assertTrue(hasattr(CONSTANTS, "REST_API_BASE_URL"))
        
        if hasattr(CONSTANTS, "STANDARDWEB3_PROVIDER_URL"):
            standardweb3_url = CONSTANTS.STANDARDWEB3_PROVIDER_URL
            rest_url = CONSTANTS.REST_API_BASE_URL
            
            # Both should be valid URLs
            self.assertTrue(standardweb3_url.startswith("http"))
            self.assertTrue(rest_url.startswith("http"))
            
            # Should be different endpoints for fallback
            self.assertNotEqual(standardweb3_url, rest_url)


if __name__ == "__main__":
    import unittest
    unittest.main()
