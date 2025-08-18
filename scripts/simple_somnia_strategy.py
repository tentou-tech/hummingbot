#!/usr/bin/env python

"""
Simple Somnia Market Making Strategy for Testing

This script demonstrates how to use the Somnia connector with a basic market making strategy.
It places small buy and sell orders around the current market price.
"""

import asyncio
import logging
import os
from decimal import Decimal

from dotenv import load_dotenv

from hummingbot.client.config.client_config_map import ClientConfigMap
from hummingbot.client.config.config_helpers import ClientConfigAdapter
from hummingbot.connector.gateway.somnia.somnia_connector import SomniaConnector
from hummingbot.core.data_type.common import OrderType, TradeType
from hummingbot.core.event.events import OrderFilledEvent

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class SimpleSomniaStrategy:
    """
    Simple market making strategy for testing Somnia connector
    """

    def __init__(self, connector: SomniaConnector, trading_pair: str):
        self.connector = connector
        self.trading_pair = trading_pair
        self.bid_spread = Decimal("0.01")  # 1% spread
        self.ask_spread = Decimal("0.01")  # 1% spread
        self.order_amount = Decimal("0.1")  # Small test amount
        self.active_orders = {}
        self.running = False

        # Subscribe to events using the correct pattern
        # self.connector.add_listener(MarketEvent.OrderFilled, self._on_order_filled)

    async def start(self):
        """Start the strategy"""
        self.running = True
        logger.info("🚀 Starting Simple Somnia Market Making Strategy")

        while self.running:
            try:
                await self._strategy_tick()
                await asyncio.sleep(10)  # Wait 10 seconds between ticks
            except KeyboardInterrupt:
                logger.info("Strategy interrupted by user")
                break
            except Exception as e:
                logger.error(f"Error in strategy tick: {e}")
                await asyncio.sleep(5)

    def stop(self):
        """Stop the strategy"""
        self.running = False
        logger.info("⏹️ Stopping strategy...")

    async def _strategy_tick(self):
        """Main strategy logic - called every tick"""
        try:
            # Get current market price from orderbook
            orderbook = await self.connector._data_source.get_new_order_book(self.trading_pair)

            bid_entries = list(orderbook.bid_entries())
            ask_entries = list(orderbook.ask_entries())

            if not bid_entries or not ask_entries:
                logger.warning("No orderbook data available")
                return

            # Get mid price
            best_bid = max(bid_entries, key=lambda x: x.price).price
            best_ask = min(ask_entries, key=lambda x: x.price).price
            mid_price = (best_bid + best_ask) / 2

            logger.info(f"📊 Market Data - Bid: {best_bid}, Ask: {best_ask}, Mid: {mid_price}")

            # Calculate our bid and ask prices
            our_bid_price = mid_price * (1 - self.bid_spread)
            our_ask_price = mid_price * (1 + self.ask_spread)

            # Check balances
            balances = self.connector.get_all_balances()
            logger.info(f"💰 Balances: {dict(balances)}")

            # For now, just log what we would do (dry run)
            logger.info(f"📈 Would place BUY order: {self.order_amount} @ {our_bid_price}")
            logger.info(f"📉 Would place SELL order: {self.order_amount} @ {our_ask_price}")

            # Uncomment below to place actual orders (be careful!)
            """
            # Place buy order
            buy_order_id = await self._place_order(
                TradeType.BUY,
                our_bid_price,
                self.order_amount
            )

            # Place sell order
            sell_order_id = await self._place_order(
                TradeType.SELL,
                our_ask_price,
                self.order_amount
            )
            """

        except Exception as e:
            logger.error(f"Error in strategy tick: {e}")

    async def _place_order(self, trade_type: TradeType, price: Decimal, amount: Decimal):
        """Place an order"""
        try:
            if trade_type == TradeType.BUY:
                order_id = await self.connector.buy(
                    trading_pair=self.trading_pair,
                    amount=amount,
                    order_type=OrderType.LIMIT,
                    price=price
                )
            else:
                order_id = await self.connector.sell(
                    trading_pair=self.trading_pair,
                    amount=amount,
                    order_type=OrderType.LIMIT,
                    price=price
                )

            logger.info(f"✅ Placed {trade_type.name} order: {order_id}")
            self.active_orders[order_id] = {"type": trade_type, "price": price, "amount": amount}
            return order_id

        except Exception as e:
            logger.error(f"❌ Failed to place {trade_type.name} order: {e}")
            return None

    def _on_order_filled(self, event: OrderFilledEvent):
        """Handle order filled events"""
        logger.info(f"🎉 Order filled: {event.order_id} - {event.trade_type.name} {event.amount} @ {event.price}")
        if event.order_id in self.active_orders:
            del self.active_orders[event.order_id]


async def test_somnia_strategy():
    """Test the Somnia connector with a simple strategy"""

    logger.info("=== Testing Somnia Connector with Simple Strategy ===")

    # Configuration
    private_key = os.getenv("SOMNIA_PRIVATE_KEY")
    if not private_key:
        logger.warning("No SOMNIA_PRIVATE_KEY found in environment, using dummy key for testing")
        private_key = "0x1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef"  # noqa: mock

    trading_pair = "0x4A3BC48C156384f9564Fd65A53a2f3D534D8f2b7-0x0ED782B8079529f7385c3eDA9fAf1EaA0DbC6a17"  # STT-USDC
    rpc_url = "https://dream-rpc.somnia.network"

    try:
        # Initialize connector
        config_map = ClientConfigMap()
        config_adapter = ClientConfigAdapter(config_map)

        connector = SomniaConnector(
            client_config_map=config_adapter,
            private_key=private_key,
            rpc_url=rpc_url,
            trading_pairs=[trading_pair]
        )

        # Start connector
        logger.info("🔌 Starting Somnia connector...")
        await connector.start_network()

        # Wait for initialization
        await asyncio.sleep(3)

        # Create and start strategy
        strategy = SimpleSomniaStrategy(connector, trading_pair)

        # Run strategy for a limited time (or until interrupted)
        logger.info("⏰ Running strategy for 60 seconds (or press Ctrl+C to stop)")
        try:
            await asyncio.wait_for(strategy.start(), timeout=60.0)
        except asyncio.TimeoutError:
            logger.info("⏰ Strategy test completed (60 seconds)")
        except KeyboardInterrupt:
            logger.info("⏹️ Strategy interrupted by user")
        finally:
            strategy.stop()

        # Stop connector
        await connector.stop_network()
        logger.info("✅ Test completed successfully!")

    except Exception as e:
        logger.error(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    print("🤖 Simple Somnia Strategy Test")
    print("===============================")
    print()
    print("This script tests the Somnia connector with a basic market making strategy.")
    print("It will:")
    print("1. Connect to Somnia testnet")
    print("2. Fetch real market data")
    print("3. Calculate bid/ask prices")
    print("4. Log what orders it would place (DRY RUN mode)")
    print()
    print("To enable actual trading, uncomment the order placement code.")
    print("⚠️  WARNING: Only use with test funds!")
    print()
    input("Press Enter to continue...")

    asyncio.run(test_somnia_strategy())
