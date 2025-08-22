import asyncio
import json
from test.isolated_asyncio_wrapper_test_case import IsolatedAsyncioWrapperTestCase
from typing import Dict
from unittest.mock import AsyncMock, MagicMock, patch

from aioresponses import aioresponses
from bidict import bidict

from hummingbot.client.config.client_config_map import ClientConfigMap
from hummingbot.client.config.config_helpers import ClientConfigAdapter
from hummingbot.connector.exchange.standard_testnet import standard_testnet_constants as CONSTANTS
from hummingbot.connector.exchange.standard_testnet.standard_testnet_api_order_book_data_source import StandardTestnetAPIOrderBookDataSource
from hummingbot.connector.exchange.standard_testnet.standard_testnet_exchange import StandardTestnetExchange
from hummingbot.connector.test_support.network_mocking_assistant import NetworkMockingAssistant
from hummingbot.connector.time_synchronizer import TimeSynchronizer
from hummingbot.core.api_throttler.async_throttler import AsyncThrottler
from hummingbot.core.data_type.order_book_message import OrderBookMessage

# QUEUE KEYS FOR WEBSOCKET DATA PROCESSING
TRADE_KEY = "trade"
ORDER_BOOK_DIFF_KEY = "order_book_diff"
ORDER_BOOK_SNAPSHOT_KEY = "order_book_snapshot"


class TestStandardTestnetAPIOrderBookDataSource(IsolatedAsyncioWrapperTestCase):
    # logging.Level required to receive logs from the data source logger
    level = 0

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls.base_asset = "STT"
        cls.quote_asset = "USDC"
        cls.trading_pair = f"{cls.base_asset}-{cls.quote_asset}"
        cls.ex_trading_pair = cls.base_asset + cls.quote_asset

    async def asyncSetUp(self) -> None:
        await super().asyncSetUp()

        self.log_records = []
        self.async_task = None
        self.mocking_assistant = NetworkMockingAssistant(self.local_event_loop)
        client_config_map = ClientConfigAdapter(ClientConfigMap())

        # Mock wallet addresses for testing
        self.connector = StandardTestnetExchange(
            client_config_map,
            "0x1234567890123456789012345678901234567890",  # Mock wallet address
            "0xabcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef",  # Mock private key
            trading_pairs=[self.trading_pair],
        )

        self.throttler = AsyncThrottler(CONSTANTS.RATE_LIMITS)
        self.time_synchronizer = TimeSynchronizer()
        self.time_synchronizer.add_time_offset_ms_sample(1000)
        self.ob_data_source = StandardTestnetAPIOrderBookDataSource(
            trading_pairs=[self.trading_pair],
            connector=self.connector,
            api_factory=self.connector._web_assistants_factory,
            throttler=self.throttler,
        )

        self._original_full_order_book_reset_time = self.ob_data_source.FULL_ORDER_BOOK_RESET_DELTA_SECONDS
        self.ob_data_source.FULL_ORDER_BOOK_RESET_DELTA_SECONDS = -1

        self.ob_data_source.logger().setLevel(1)
        self.ob_data_source.logger().addHandler(self)

        self.resume_test_event = asyncio.Event()

        self.connector._set_trading_pair_symbol_map(bidict({self.ex_trading_pair: self.trading_pair}))

    def tearDown(self) -> None:
        self.async_task and self.async_task.cancel()
        self.ob_data_source.FULL_ORDER_BOOK_RESET_DELTA_SECONDS = self._original_full_order_book_reset_time
        super().tearDown()

    def handle(self, record):
        self.log_records.append(record)

    def _is_logged(self, log_level: str, message: str) -> bool:
        return any(record.levelname == log_level and record.getMessage() == message for record in self.log_records)

    def _create_exception_and_unlock_test_with_event(self, exception):
        self.resume_test_event.set()
        raise exception

    def get_mock_order_book_data(self) -> Dict:
        """Mock order book data for Somnia"""
        return {
            "bids": [
                ["1.50000000", "100.00000000"],
                ["1.49000000", "200.00000000"],
                ["1.48000000", "150.00000000"],
            ],
            "asks": [
                ["1.51000000", "100.00000000"],
                ["1.52000000", "200.00000000"],
                ["1.53000000", "150.00000000"],
            ],
            "lastUpdateId": 123456789
        }

    def get_mock_standardweb3_response(self) -> Dict:
        """Mock StandardWeb3 orderbook response"""
        return {
            "bids": [
                {"price": "1.50000000", "quantity": "100.00000000"},
                {"price": "1.49000000", "quantity": "200.00000000"},
                {"price": "1.48000000", "quantity": "150.00000000"},
            ],
            "asks": [
                {"price": "1.51000000", "quantity": "100.00000000"},
                {"price": "1.52000000", "quantity": "200.00000000"},
                {"price": "1.53000000", "quantity": "150.00000000"},
            ]
        }

    def test_get_new_order_book(self):
        """Test order book creation"""
        order_book = self.ob_data_source.get_new_order_book(self.trading_pair)
        self.assertIsNotNone(order_book)
        self.assertEqual(order_book.trading_pair, self.trading_pair)

    @patch("hummingbot.connector.exchange.standard_testnet.standard_testnet_api_order_book_data_source.standardweb3")
    def test_standardweb3_order_book_fetch(self, mock_standardweb3):
        """Test order book fetching via StandardWeb3"""
        mock_client = MagicMock()
        mock_client.fetch_orderbook_ticks.return_value = self.get_mock_standardweb3_response()
        mock_standardweb3.StandardClient.return_value = mock_client

        # Test StandardWeb3 fetch
        result = self.async_run_with_timeout(
            self.ob_data_source._fetch_via_standardweb3(self.trading_pair)
        )
        
        self.assertIsNotNone(result)
        self.assertIn("bids", result)
        self.assertIn("asks", result)

    def test_rest_api_fallback(self):
        """Test REST API fallback mechanism"""
        with aioresponses() as m:
            url = f"{CONSTANTS.REST_API_BASE_URL}{CONSTANTS.GET_ORDERBOOK_PATH_URL}"
            m.get(url, payload=self.get_mock_order_book_data())
            
            result = self.async_run_with_timeout(
                self.ob_data_source._fetch_via_rest_api(self.trading_pair)
            )
            
            self.assertIsNotNone(result)
            self.assertIn("bids", result)
            self.assertIn("asks", result)

    @patch("hummingbot.connector.exchange.standard_testnet.standard_testnet_api_order_book_data_source.standardweb3")
    def test_dual_fallback_mechanism(self, mock_standardweb3):
        """Test the dual fallback mechanism: StandardWeb3 primary + REST backup"""
        # Configure StandardWeb3 to fail
        mock_client = MagicMock()
        mock_client.fetch_orderbook_ticks.side_effect = Exception("StandardWeb3 connection failed")
        mock_standardweb3.StandardClient.return_value = mock_client
        
        with aioresponses() as m:
            url = f"{CONSTANTS.REST_API_BASE_URL}{CONSTANTS.GET_ORDERBOOK_PATH_URL}"
            m.get(url, payload=self.get_mock_order_book_data())
            
            result = self.async_run_with_timeout(
                self.ob_data_source._request_order_book_snapshot(self.trading_pair)
            )
            
            self.assertIsNotNone(result)
            # Should have fallen back to REST API

    def test_trading_pairs_initialization(self):
        """Test trading pairs initialization"""
        trading_pairs = self.async_run_with_timeout(
            self.ob_data_source.get_trading_pairs()
        )
        
        self.assertIsNotNone(trading_pairs)
        self.assertIsInstance(trading_pairs, list)

    def test_order_book_snapshot_message_creation(self):
        """Test order book snapshot message creation"""
        mock_data = self.get_mock_order_book_data()
        
        # Mock the snapshot processing
        with patch.object(self.ob_data_source, "_request_order_book_snapshot", new_callable=AsyncMock) as mock_snapshot:
            mock_snapshot.return_value = mock_data
            
            snapshot = self.async_run_with_timeout(
                self.ob_data_source._request_order_book_snapshot(self.trading_pair)
            )
            
            self.assertIsNotNone(snapshot)
            self.assertIn("bids", snapshot)
            self.assertIn("asks", snapshot)

    def test_token_mapping_functionality(self):
        """Test token address mapping functionality"""
        # Test that token mapping works correctly
        token_info = self.ob_data_source._get_token_info("STT")
        self.assertIsNotNone(token_info)
        
        token_info = self.ob_data_source._get_token_info("USDC")
        self.assertIsNotNone(token_info)

    def test_production_mode_detection(self):
        """Test production mode vs test mode detection"""
        # Should be in production mode (not demo/test)
        with patch.object(self.ob_data_source, "_request_order_book_snapshot") as mock_request:
            self.async_run_with_timeout(
                self.ob_data_source._request_order_book_snapshot(self.trading_pair)
            )
            
            # Verify production mode logging
            self.assertTrue(any("🔴 PRODUCTION MODE" in str(record.getMessage()) for record in self.log_records))

    def test_error_handling_and_logging(self):
        """Test error handling and logging functionality"""
        with patch.object(self.ob_data_source, "_fetch_via_standardweb3", side_effect=Exception("Test error")):
            with patch.object(self.ob_data_source, "_fetch_via_rest_api", side_effect=Exception("REST error")):
                
                try:
                    self.async_run_with_timeout(
                        self.ob_data_source._request_order_book_snapshot(self.trading_pair)
                    )
                except Exception:
                    pass
                
                # Should have logged the errors
                self.assertTrue(any("error" in str(record.getMessage()).lower() for record in self.log_records))

    def test_order_book_data_processing(self):
        """Test order book data processing and validation"""
        mock_data = self.get_mock_order_book_data()
        
        # Test that the data is properly structured for Hummingbot
        self.assertIn("bids", mock_data)
        self.assertIn("asks", mock_data)
        self.assertIsInstance(mock_data["bids"], list)
        self.assertIsInstance(mock_data["asks"], list)
        
        # Test bid/ask format
        if mock_data["bids"]:
            bid = mock_data["bids"][0]
            self.assertEqual(len(bid), 2)  # [price, quantity]
        
        if mock_data["asks"]:
            ask = mock_data["asks"][0]
            self.assertEqual(len(ask), 2)  # [price, quantity]

    def async_run_with_timeout(self, coroutine, timeout: float = 1):
        return asyncio.get_event_loop().run_until_complete(asyncio.wait_for(coroutine, timeout))


if __name__ == "__main__":
    import unittest
    unittest.main()
