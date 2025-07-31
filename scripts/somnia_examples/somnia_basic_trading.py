#!/usr/bin/env python

"""
This script demonstrates how to use the Somnia connector for basic trading operations.
"""

import asyncio
import logging
from decimal import Decimal

from hummingbot.client.config.config_helpers import ClientConfigAdapter
from hummingbot.connector.gateway.somnia.somnia_connector import SomniaConnector
from hummingbot.core.data_type.common import OrderType, TradeType

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configuration
PRIVATE_KEY = "your_private_key_here"  # Replace with your private key
RPC_URL = "https://dream-rpc.somnia.network"  # Somnia testnet RPC URL
TRADING_PAIR = "ATOM-USDC"  # Example trading pair


async def main():
    """Main function to demonstrate the Somnia connector"""

    try:
        # Create an empty config adapter
        client_config_map = ClientConfigAdapter(ClientConfigAdapter.create_empty_config_dict())

        # Initialize the connector
        connector = SomniaConnector(
            client_config_map=client_config_map,
            private_key=PRIVATE_KEY,
            rpc_url=RPC_URL,
            trading_pairs=[TRADING_PAIR],
            trading_required=True
        )

        # Start the connector
        await connector.start_network()
        logger.info("Somnia connector started")

        # Wait for the connector to be ready
        await asyncio.sleep(5)

        # Fetch and display account balances
        await connector._update_balances()
        logger.info(f"Account balances: {connector._account_balances}")

        # Get order book
        data_source = connector._data_source
        order_book = await data_source.get_new_order_book(TRADING_PAIR)

        best_bid = order_book.get_price(is_buy=True)
        best_ask = order_book.get_price(is_buy=False)

        logger.info(f"Order book for {TRADING_PAIR}:")
        logger.info(f"Best bid: {best_bid}")
        logger.info(f"Best ask: {best_ask}")

        # Calculate prices for orders
        mid_price = (best_bid + best_ask) / Decimal("2")
        buy_price = mid_price * Decimal("0.99")  # 1% below mid price
        sell_price = mid_price * Decimal("1.01")  # 1% above mid price

        # Place a buy limit order
        buy_amount = Decimal("0.1")  # Amount in base asset
        buy_client_order_id = "somnia_demo_buy_1"

        logger.info(f"Placing buy limit order: {buy_amount} {TRADING_PAIR} at {buy_price}")

        buy_tx_hash, buy_timestamp = await connector._create_order(
            trade_type=TradeType.BUY,
            order_id=buy_client_order_id,
            trading_pair=TRADING_PAIR,
            amount=buy_amount,
            order_type=OrderType.LIMIT,
            price=buy_price
        )

        logger.info(f"Buy order placed with tx hash: {buy_tx_hash}")

        # Wait for the buy order to be processed
        await asyncio.sleep(10)

        # Place a sell limit order
        sell_amount = Decimal("0.1")  # Amount in base asset
        sell_client_order_id = "somnia_demo_sell_1"

        logger.info(f"Placing sell limit order: {sell_amount} {TRADING_PAIR} at {sell_price}")

        sell_tx_hash, sell_timestamp = await connector._create_order(
            trade_type=TradeType.SELL,
            order_id=sell_client_order_id,
            trading_pair=TRADING_PAIR,
            amount=sell_amount,
            order_type=OrderType.LIMIT,
            price=sell_price
        )

        logger.info(f"Sell order placed with tx hash: {sell_tx_hash}")

        # Wait for a while to monitor events
        logger.info("Waiting for events...")
        await asyncio.sleep(30)

        # Cancel the orders if they're still active
        for order_id in [buy_client_order_id, sell_client_order_id]:
            logger.info(f"Cancelling order {order_id}")
            cancellation_result = await connector._execute_cancel(order_id, 60)
            logger.info(f"Cancellation result for {order_id}: {cancellation_result}")

    except Exception as e:
        logger.error(f"Error in demo script: {e}", exc_info=True)
    finally:
        # Stop the connector
        await connector.stop_network()
        logger.info("Somnia connector stopped")

if __name__ == "__main__":
    # Run the demo
    asyncio.run(main())
