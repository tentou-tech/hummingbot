#!/usr/bin/env python

import unittest
import unittest.mock
from decimal import Decimal

from hummingbot.connector.gateway.somnia.somnia_connector import SomniaConnector
from hummingbot.core.data_type.common import OrderType, TradeType


class SomniaConnectorUnitTest(unittest.TestCase):
    # Mock client config map
    client_config_map = {}

    # Test private key (not a real key)
    private_key = "0x1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef"  # noqa: mock

    # Test RPC URL
    rpc_url = "https://dream-rpc.somnia.network"

    # Test trading pairs
    trading_pairs = ["ATOM-USDC"]

    @unittest.mock.patch("standardweb3.StandardClient")
    def setUp(self, mock_standard_client):
        # Mock the StandardClient
        self.mock_standard_client = mock_standard_client.return_value
        self.mock_standard_client.address = "0xmockaddress"

        # Mock methods
        self.mock_standard_client.get_balance = unittest.mock.AsyncMock()
        self.mock_standard_client.fetch_orderbook = unittest.mock.AsyncMock()
        self.mock_standard_client.limit_buy = unittest.mock.AsyncMock()
        self.mock_standard_client.limit_sell = unittest.mock.AsyncMock()
        self.mock_standard_client.market_buy = unittest.mock.AsyncMock()
        self.mock_standard_client.market_sell = unittest.mock.AsyncMock()
        self.mock_standard_client.cancel_order = unittest.mock.AsyncMock()
        self.mock_standard_client.approve_token = unittest.mock.AsyncMock()

        # Configure mock return values
        self.mock_standard_client.get_balance.return_value = "100.0"
        self.mock_standard_client.fetch_orderbook.return_value = {
            "asks": [{"price": "10.5", "amount": "1.0"}],
            "bids": [{"price": "10.0", "amount": "2.0"}]
        }
        self.mock_standard_client.limit_buy.return_value = "0xtxhash"
        self.mock_standard_client.limit_sell.return_value = "0xtxhash"
        self.mock_standard_client.market_buy.return_value = "0xtxhash"
        self.mock_standard_client.market_sell.return_value = "0xtxhash"
        self.mock_standard_client.cancel_order.return_value = "0xtxhash"
        self.mock_standard_client.approve_token.return_value = "0xtxhash"

        # Create the connector
        self.connector = SomniaConnector(
            client_config_map=self.client_config_map,
            private_key=self.private_key,
            rpc_url=self.rpc_url,
            trading_pairs=self.trading_pairs,
            trading_required=True
        )

        # Replace the StandardClient instance with our mock
        self.connector._standard_client = self.mock_standard_client

    def test_connector_initialization(self):
        """Test if connector is properly initialized"""
        self.assertEqual(self.connector._name, "somnia")
        self.assertEqual(self.connector._trading_pairs, self.trading_pairs)
        self.assertTrue(self.connector._trading_required)

    async def test_get_order_price_quote(self):
        """Test getting order price quote"""
        # Test buy price quote (should return ask price)
        buy_price = await self.connector.get_order_price_quote(
            trading_pair="ATOM-USDC",
            is_buy=True,
            amount=Decimal("1.0")
        )
        self.assertEqual(buy_price, Decimal("10.5"))

        # Test sell price quote (should return bid price)
        sell_price = await self.connector.get_order_price_quote(
            trading_pair="ATOM-USDC",
            is_buy=False,
            amount=Decimal("1.0")
        )
        self.assertEqual(sell_price, Decimal("10.0"))

    async def test_create_buy_limit_order(self):
        """Test creating a buy limit order"""
        # Create a buy limit order
        order_id = "test_order_id"
        amount = Decimal("1.0")
        price = Decimal("10.0")

        tx_hash, timestamp = await self.connector._create_order(
            trade_type=TradeType.BUY,
            order_id=order_id,
            trading_pair="ATOM-USDC",
            amount=amount,
            order_type=OrderType.LIMIT,
            price=price
        )

        # Check if StandardClient's limit_buy was called with correct parameters
        self.mock_standard_client.limit_buy.assert_called_once()
        args, kwargs = self.mock_standard_client.limit_buy.call_args

        self.assertEqual(kwargs["base"], "ATOM")
        self.assertEqual(kwargs["quote"], "USDC")
        self.assertEqual(kwargs["price"], "10.0")
        self.assertEqual(kwargs["quote_amount"], "10.0")  # 1.0 * 10.0
        self.assertEqual(kwargs["uid"], "test_order_id")

        # Check return values
        self.assertEqual(tx_hash, "0xtxhash")
        self.assertTrue(isinstance(timestamp, float))

    async def test_create_sell_limit_order(self):
        """Test creating a sell limit order"""
        # Create a sell limit order
        order_id = "test_order_id"
        amount = Decimal("1.0")
        price = Decimal("10.0")

        tx_hash, timestamp = await self.connector._create_order(
            trade_type=TradeType.SELL,
            order_id=order_id,
            trading_pair="ATOM-USDC",
            amount=amount,
            order_type=OrderType.LIMIT,
            price=price
        )

        # Check if StandardClient's limit_sell was called with correct parameters
        self.mock_standard_client.limit_sell.assert_called_once()
        args, kwargs = self.mock_standard_client.limit_sell.call_args

        self.assertEqual(kwargs["base"], "ATOM")
        self.assertEqual(kwargs["quote"], "USDC")
        self.assertEqual(kwargs["price"], "10.0")
        self.assertEqual(kwargs["base_amount"], "1.0")
        self.assertEqual(kwargs["uid"], "test_order_id")

        # Check return values
        self.assertEqual(tx_hash, "0xtxhash")
        self.assertTrue(isinstance(timestamp, float))

    async def test_approve_token(self):
        """Test token approval"""
        token_symbol = "ATOM"
        amount = Decimal("10.0")

        tx_hash = await self.connector.approve_token(token_symbol, amount)

        # Check if StandardClient's approve_token was called with correct parameters
        self.mock_standard_client.approve_token.assert_called_once()
        args, kwargs = self.mock_standard_client.approve_token.call_args

        self.assertEqual(args[0], "ATOM")
        self.assertEqual(args[1], "10.0")

        # Check return value
        self.assertEqual(tx_hash, "0xtxhash")


# Enable running test directly
if __name__ == "__main__":
    unittest.main()
