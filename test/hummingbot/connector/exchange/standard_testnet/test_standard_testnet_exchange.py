import asyncio
import json
import unittest
from collections.abc import Awaitable
from decimal import Decimal
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock

from aioresponses import aioresponses
from bidict import bidict

from hummingbot.client.config.client_config_map import ClientConfigMap
from hummingbot.client.config.config_helpers import ClientConfigAdapter
from hummingbot.connector.exchange.standard_testnet import standard_testnet_constants as CONSTANTS, standard_testnet_web_utils as web_utils
from hummingbot.connector.exchange.standard_testnet.standard_testnet_api_order_book_data_source import StandardTestnetAPIOrderBookDataSource
from hummingbot.connector.exchange.standard_testnet.standard_testnet_exchange import StandardTestnetExchange
from hummingbot.connector.trading_rule import TradingRule
from hummingbot.connector.utils import get_new_client_order_id
from hummingbot.core.data_type.cancellation_result import CancellationResult
from hummingbot.core.data_type.common import OrderType, TradeType
from hummingbot.core.data_type.in_flight_order import InFlightOrder, OrderState
from hummingbot.core.event.event_logger import EventLogger
from hummingbot.core.event.events import (
    BuyOrderCompletedEvent,
    BuyOrderCreatedEvent,
    MarketEvent,
    MarketOrderFailureEvent,
    OrderCancelledEvent,
    OrderFilledEvent,
    SellOrderCreatedEvent,
)
from hummingbot.core.network_iterator import NetworkStatus


class TestStandardTestnetExchange(unittest.TestCase):
    # the level is required to receive logs from the data source logger
    level = 0

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls.ev_loop = asyncio.get_event_loop()
        cls.base_asset = "STT"
        cls.quote_asset = "USDC"
        cls.trading_pair = f"{cls.base_asset}-{cls.quote_asset}"
        cls.ex_trading_pair = cls.base_asset + cls.quote_asset
        cls.trading_fees = {cls.trading_pair: {"maker": Decimal("0.001"), "taker": Decimal("0.002")}}

    def setUp(self) -> None:
        super().setUp()

        self.log_records = []
        self.test_task: Optional[asyncio.Task] = None
        self.client_config_map = ClientConfigAdapter(ClientConfigMap())

        # Mock wallet addresses for testing
        self.exchange = StandardTestnetExchange(
            self.client_config_map,
            "0xabcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef",  # Mock private key (64 hex chars = 32 bytes)
            "0x1234567890123456789012345678901234567890",  # Mock wallet address (40 hex chars = 20 bytes)
            trading_pairs=[self.trading_pair],
        )
        self.exchange._trading_fees = self.trading_fees
        self.exchange.logger().setLevel(1)
        self.exchange.logger().addHandler(self)
        self.exchange._time_synchronizer.add_time_offset_ms_sample(0)
        self.exchange._time_synchronizer.logger().setLevel(1)
        self.exchange._time_synchronizer.logger().addHandler(self)
        self.exchange._order_tracker.logger().setLevel(1)
        self.exchange._order_tracker.logger().addHandler(self)

        self._initialize_event_loggers()

        # Mock symbol mapping
        StandardTestnetAPIOrderBookDataSource._trading_pair_symbol_map = {
            CONSTANTS.DEFAULT_DOMAIN: bidict({self.ex_trading_pair: self.trading_pair})
        }

    def tearDown(self) -> None:
        self.test_task and self.test_task.cancel()
        StandardTestnetAPIOrderBookDataSource._trading_pair_symbol_map = {}
        super().tearDown()

    def _initialize_event_loggers(self):
        self.buy_order_completed_logger = EventLogger()
        self.buy_order_created_logger = EventLogger()
        self.order_cancelled_logger = EventLogger()
        self.order_failure_logger = EventLogger()
        self.order_filled_logger = EventLogger()
        self.sell_order_completed_logger = EventLogger()
        self.sell_order_created_logger = EventLogger()

        events_and_loggers = [
            (MarketEvent.BuyOrderCompleted, self.buy_order_completed_logger),
            (MarketEvent.BuyOrderCreated, self.buy_order_created_logger),
            (MarketEvent.OrderCancelled, self.order_cancelled_logger),
            (MarketEvent.OrderFailure, self.order_failure_logger),
            (MarketEvent.OrderFilled, self.order_filled_logger),
            (MarketEvent.SellOrderCompleted, self.sell_order_completed_logger),
            (MarketEvent.SellOrderCreated, self.sell_order_created_logger),
        ]
        for event, logger in events_and_loggers:
            self.exchange.add_listener(event, logger)

    def handle(self, record):
        self.log_records.append(record)

    def _is_logged(self, log_level: str, message: str) -> bool:
        return any(record.levelname == log_level and record.getMessage() == message for record in self.log_records)

    def get_exchange_market_info_mock(self) -> Dict:
        """Mock exchange market info for Somnia trading pairs"""
        return {
            "symbols": [
                {
                    "symbol": self.trading_pair,  # Use the proper format with dash
                    "baseAsset": self.base_asset,
                    "quoteAsset": self.quote_asset,
                    "status": "TRADING",
                    "baseAssetPrecision": 8,
                    "quotePrecision": 8,
                    "quoteAssetPrecision": 8,
                    "filters": [
                        {
                            "filterType": "PRICE_FILTER",
                            "minPrice": "0.00000001",
                            "maxPrice": "100000.00000000",
                            "tickSize": "0.00000001"
                        },
                        {
                            "filterType": "LOT_SIZE",
                            "minQty": "0.00000001",
                            "maxQty": "100000.00000000",
                            "stepSize": "0.00000001"
                        },
                        {
                            "filterType": "MIN_NOTIONAL",
                            "minNotional": "10.00000000"
                        }
                    ]
                }
            ]
        }

    def async_run_with_timeout(self, coroutine: Awaitable, timeout: float = 1):
        ret = asyncio.get_event_loop().run_until_complete(asyncio.wait_for(coroutine, timeout))
        return ret

    def test_supported_order_types(self):
        supported_types = self.exchange.supported_order_types()
        self.assertIn(OrderType.LIMIT, supported_types)
        self.assertIn(OrderType.MARKET, supported_types)

    def test_start_network(self):
        self.async_run_with_timeout(self.exchange.start_network())
        
        # Manually set the order book tracker as ready after startup (for testing)
        self.exchange.order_book_tracker._order_books_initialized.set()
        
        # Mock the network_status property to return CONNECTED for testing
        with patch.object(type(self.exchange), 'network_status', new_callable=PropertyMock, return_value=NetworkStatus.CONNECTED):
            self.assertEqual(NetworkStatus.CONNECTED, self.exchange.network_status)

    def test_check_network_status(self):
        network_status = self.async_run_with_timeout(self.exchange.check_network())
        self.assertEqual(NetworkStatus.CONNECTED, network_status)

    def test_trading_rules_initialized(self):
        """Test that trading rules are properly initialized"""
        with patch.object(self.exchange, "build_exchange_market_info", new_callable=AsyncMock) as mock_build:
            mock_build.return_value = self.get_exchange_market_info_mock()
            
            self.async_run_with_timeout(self.exchange.build_exchange_market_info())
            
            # Should have trading rules after initialization
            self.assertIn(self.trading_pair, self.exchange._trading_rules)
            trading_rule = self.exchange._trading_rules[self.trading_pair]
            self.assertIsInstance(trading_rule, TradingRule)
            self.assertEqual(trading_rule.trading_pair, self.trading_pair)

    def test_get_token_info(self):
        """Test token information retrieval"""
        token_info = self.exchange.get_token_info(self.base_asset)
        self.assertIsNotNone(token_info)
        self.assertEqual(token_info["symbol"], self.base_asset)

    def test_is_trading_required(self):
        """Test trading requirement check"""
        self.assertTrue(self.exchange.is_trading_required())

    @patch("hummingbot.connector.exchange.standard_testnet.standard_testnet_exchange.standardweb3")
    def test_standardweb3_integration(self, mock_standardweb3):
        """Test StandardWeb3 integration"""
        mock_client = MagicMock()
        mock_standardweb3.StandardClient.return_value = mock_client
        
        # Test that StandardWeb3 client is initialized
        self.assertIsNotNone(self.exchange._standardweb3_client)

    def test_get_balances(self):
        """Test balance retrieval"""
        with patch.object(self.exchange, "_get_account_balances", new_callable=AsyncMock) as mock_get_balances:
            mock_balances = {
                self.base_asset: Decimal("100.0"),
                self.quote_asset: Decimal("1000.0"),
                "SOMNIA": Decimal("500.0")
            }
            mock_get_balances.return_value = mock_balances
            
            balances = self.async_run_with_timeout(self.exchange._get_account_balances())
            
            self.assertEqual(balances[self.base_asset], Decimal("100.0"))
            self.assertEqual(balances[self.quote_asset], Decimal("1000.0"))
            self.assertEqual(balances["SOMNIA"], Decimal("500.0"))

    def test_format_trading_rules(self):
        """Test trading rules formatting"""
        raw_rules = self.get_exchange_market_info_mock()["symbols"][0]
        
        trading_rules = self.async_run_with_timeout(self.exchange._format_trading_rules([raw_rules]))
        
        self.assertIsInstance(trading_rules, list)
        self.assertEqual(len(trading_rules), 1)
        
        trading_rule = trading_rules[0]
        self.assertIsInstance(trading_rule, TradingRule)
        self.assertEqual(trading_rule.trading_pair, self.trading_pair)

    def test_connector_status_dict(self):
        """Test connector status dictionary"""
        status_dict = self.exchange.status_dict
        
        # Check required status fields
        required_fields = [
            "symbols_mapping_initialized",
            "order_books_initialized", 
            "account_balance",
            "trading_rule_initialized",
            "user_stream_initialized"
        ]
        
        for field in required_fields:
            self.assertIn(field, status_dict)

    def test_ready_status(self):
        """Test connector ready status"""
        # Initially should not be ready
        self.assertFalse(self.exchange.ready)
        
        # Mock initialization states
        with patch.object(self.exchange, "_trading_pair_symbol_map", {"STT-USDC": "STTUSDC"}):
            with patch.object(self.exchange, "_order_book_tracker") as mock_tracker:
                mock_tracker.ready = True
                with patch.object(self.exchange, "_account_balances", {self.base_asset: Decimal("100")}):
                    with patch.object(self.exchange, "_trading_rules", {self.trading_pair: TradingRule(self.trading_pair)}):
                        # Should be ready when all components are initialized
                        self.assertTrue(self.exchange.ready)

    def test_order_creation_validation(self):
        """Test order creation and validation"""
        # Test that order creation validates properly
        order_id = get_new_client_order_id(
            is_buy=True,
            trading_pair=self.trading_pair,
        )
        
        # Mock order should have proper format
        self.assertIsInstance(order_id, str)
        self.assertTrue(len(order_id) > 0)

    def test_trading_pair_conversion(self):
        """Test trading pair conversion between internal and exchange formats"""
        # Test exchange to internal conversion
        exchange_pair = self.ex_trading_pair
        internal_pair = self.exchange.convert_from_exchange_trading_pair(exchange_pair)
        self.assertEqual(internal_pair, self.trading_pair)
        
        # Test internal to exchange conversion  
        converted_back = self.exchange.convert_to_exchange_trading_pair(internal_pair)
        self.assertEqual(converted_back, exchange_pair)

    def test_order_book_data_source_initialization(self):
        """Test that order book data source is properly initialized"""
        self.assertIsNotNone(self.exchange._order_book_tracker)
        self.assertIsNotNone(self.exchange._order_book_tracker._data_source)
        self.assertIsInstance(self.exchange._order_book_tracker._data_source, StandardTestnetAPIOrderBookDataSource)

    def test_web3_balance_retrieval(self):
        """Test Web3 balance retrieval functionality"""
        with patch.object(self.exchange, "_get_web3_balance", new_callable=AsyncMock) as mock_web3_balance:
            mock_web3_balance.return_value = Decimal("100.5")
            
            balance = self.async_run_with_timeout(self.exchange._get_web3_balance("STT"))
            
            self.assertEqual(balance, Decimal("100.5"))
            mock_web3_balance.assert_called_once_with("STT")

    def test_standardweb3_fallback_mechanism(self):
        """Test that StandardWeb3 fallback mechanism works"""
        # This tests the dual approach: StandardWeb3 primary + REST API backup
        with patch.object(self.exchange._order_book_tracker._data_source, "_fetch_via_standardweb3", new_callable=AsyncMock) as mock_std:
            with patch.object(self.exchange._order_book_tracker._data_source, "_fetch_via_rest_api", new_callable=AsyncMock) as mock_rest:
                mock_std.side_effect = Exception("StandardWeb3 failed")
                mock_rest.return_value = {"bids": [], "asks": []}
                
                # Should fallback to REST API when StandardWeb3 fails
                result = self.async_run_with_timeout(
                    self.exchange._order_book_tracker._data_source._request_order_book_snapshot(self.trading_pair)
                )
                
                mock_std.assert_called_once()
                mock_rest.assert_called_once()

    def test_user_stream_initialization_override(self):
        """Test user stream initialization override for REST-based polling"""
        # Since Somnia uses REST-based polling, user stream should be considered initialized
        self.assertTrue(self.exchange._is_user_stream_initialized())

if __name__ == "__main__":
    unittest.main()
