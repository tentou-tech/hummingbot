#!/usr/bin/env python

import unittest
import unittest.mock
from decimal import Decimal

from hummingbot.connector.gateway.somnia.somnia_data_source import SomniaOrderBookDataSource
from hummingbot.core.data_type.order_book import OrderBook
from hummingbot.core.data_type.order_book_message import OrderBookMessageType


class SomniaOrderBookDataSourceUnitTest(unittest.TestCase):
    # Test trading pairs
    trading_pairs = ["ATOM-USDC"]

    @unittest.mock.patch("standardweb3.StandardClient")
    @unittest.mock.patch("hummingbot.connector.gateway.somnia.somnia_data_source.execute_graphql_query")
    def setUp(self, mock_execute_graphql, mock_standard_client):
        # Mock StandardClient
        self.mock_standard_client = mock_standard_client.return_value

        # Mock methods
        self.mock_standard_client.fetch_orderbook = unittest.mock.AsyncMock()

        # Configure mock return values
        self.mock_standard_client.fetch_orderbook.return_value = {
            "asks": [
                {"price": "10.5", "amount": "1.0"},
                {"price": "11.0", "amount": "2.0"}
            ],
            "bids": [
                {"price": "10.0", "amount": "2.0"},
                {"price": "9.5", "amount": "3.0"}
            ]
        }

        # Mock GraphQL query execution
        self.mock_execute_graphql = mock_execute_graphql
        self.mock_execute_graphql.return_value = {
            "data": {
                "sellOrders": [
                    {"id": "sell1", "price": "10.5", "baseAmount": "1.0", "quoteAmount": "10.5", "side": 1},
                    {"id": "sell2", "price": "11.0", "baseAmount": "2.0", "quoteAmount": "22.0", "side": 1}
                ],
                "buyOrders": [
                    {"id": "buy1", "price": "10.0", "baseAmount": "2.0", "quoteAmount": "20.0", "side": 0},
                    {"id": "buy2", "price": "9.5", "baseAmount": "3.0", "quoteAmount": "28.5", "side": 0}
                ],
                "trades": [
                    {
                        "id": "trade1",
                        "order": {"id": "order1", "side": 0},
                        "transaction": {"id": "tx1"},
                        "baseToken": {"symbol": "ATOM"},
                        "quoteToken": {"symbol": "USDC"},
                        "baseAmount": "1.0",
                        "quoteAmount": "10.0",
                        "price": "10.0",
                        "timestamp": "1620000000"
                    }
                ]
            }
        }

        # Create the data source
        self.data_source = SomniaOrderBookDataSource(
            trading_pairs=self.trading_pairs,
            standard_client=self.mock_standard_client
        )

    async def test_get_new_order_book_from_standard_client(self):
        """Test creating a new order book from StandardClient data"""
        # Get the order book
        order_book = await self.data_source.get_new_order_book("ATOM-USDC")

        # Check if StandardClient's fetch_orderbook was called
        self.mock_standard_client.fetch_orderbook.assert_called_once()
        args, kwargs = self.mock_standard_client.fetch_orderbook.call_args
        self.assertEqual(kwargs["base"], "ATOM")
        self.assertEqual(kwargs["quote"], "USDC")

        # Verify order book content
        self.assertTrue(isinstance(order_book, OrderBook))
        self.assertEqual(len(order_book.ask_entries()), 2)
        self.assertEqual(len(order_book.bid_entries()), 2)

        # Check specific prices
        self.assertEqual(order_book.get_price(is_buy=True), Decimal("10.0"))  # highest bid
        self.assertEqual(order_book.get_price(is_buy=False), Decimal("10.5"))  # lowest ask

    async def test_get_new_order_book_from_graphql_fallback(self):
        """Test creating a new order book from GraphQL API fallback"""
        # Force StandardClient to raise exception to test fallback
        self.mock_standard_client.fetch_orderbook.side_effect = Exception("Test exception")

        # Get the order book
        order_book = await self.data_source.get_new_order_book("ATOM-USDC")

        # Check if StandardClient's fetch_orderbook was called
        self.mock_standard_client.fetch_orderbook.assert_called_once()

        # Check if GraphQL query was executed as fallback
        self.mock_execute_graphql.assert_called_once()

        # Verify order book content
        self.assertTrue(isinstance(order_book, OrderBook))
        self.assertEqual(len(order_book.ask_entries()), 2)
        self.assertEqual(len(order_book.bid_entries()), 2)

        # Check specific prices
        self.assertEqual(order_book.get_price(is_buy=True), Decimal("10.0"))  # highest bid
        self.assertEqual(order_book.get_price(is_buy=False), Decimal("10.5"))  # lowest ask

    async def test_get_last_traded_prices(self):
        """Test fetching last traded prices"""
        # Set up mock for recent trades query
        self.mock_execute_graphql.return_value = {
            "data": {
                "trades": [
                    {
                        "id": "trade1",
                        "order": {"id": "order1", "side": 0},
                        "transaction": {"id": "tx1"},
                        "baseToken": {"symbol": "ATOM"},
                        "quoteToken": {"symbol": "USDC"},
                        "baseAmount": "1.0",
                        "quoteAmount": "10.0",
                        "price": "10.0",
                        "timestamp": "1620000000"
                    }
                ]
            }
        }

        # Get last traded prices
        prices = await self.data_source.get_last_traded_prices(["ATOM-USDC"])

        # Verify prices
        self.assertEqual(len(prices), 1)
        self.assertEqual(prices["ATOM-USDC"], Decimal("10.0"))

    async def test_order_book_snapshot_message(self):
        """Test creating an order book snapshot message"""
        # Get the snapshot message
        snapshot_msg = await self.data_source._order_book_snapshot("ATOM-USDC")

        # Verify message type
        self.assertEqual(snapshot_msg.type, OrderBookMessageType.SNAPSHOT)

        # Verify message content
        content = snapshot_msg.content
        self.assertEqual(content["trading_pair"], "ATOM-USDC")
        self.assertTrue("update_id" in content)
        self.assertTrue("bids" in content)
        self.assertTrue("asks" in content)

        # Check order book data
        self.assertEqual(len(content["bids"]), 2)
        self.assertEqual(len(content["asks"]), 2)

        # Check specific prices
        self.assertEqual(content["bids"][0][0], 10.0)  # highest bid price
        self.assertEqual(content["asks"][0][0], 10.5)  # lowest ask price


# Enable running test directly
if __name__ == "__main__":
    unittest.main()
