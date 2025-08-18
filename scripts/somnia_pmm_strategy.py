#!/usr/bin/env python

"""
Simple PMM Strategy adapted for Somnia Connector

This is a simple Pure Market Making (PMM) strategy specifically designed for the Somnia connector.
It demonstrates how to use Hummingbot's strategy framework with your custom connector.
"""

import os
from decimal import Decimal
from typing import Dict

from pydantic import Field

from hummingbot.client.config.config_data_types import BaseClientModel, ClientFieldData
from hummingbot.connector.connector_base import ConnectorBase
from hummingbot.core.data_type.common import OrderType, TradeType
from hummingbot.core.data_type.order_candidate import OrderCandidate
from hummingbot.core.event.events import OrderFilledEvent
from hummingbot.strategy.script_strategy_base import ScriptStrategyBase


class SomniaPMMConfig(BaseClientModel):
    script_file_name: str = os.path.basename(__file__)
    exchange: str = Field("somnia", client_data=ClientFieldData(prompt_on_new=True, prompt="Enter the exchange name"))
    trading_pair: str = Field("0xb35a7935F8fbc52fB525F16Af09329b3794E8C42-0x0ED782B8079529f7385c3eDA9fAf1EaA0DbC6a17",
                              client_data=ClientFieldData(prompt_on_new=True, prompt="Enter the trading pair"))
    order_amount: Decimal = Field(Decimal("0.01"), client_data=ClientFieldData(prompt_on_new=True, prompt="Enter the order amount"))
    bid_spread: Decimal = Field(Decimal("0.01"), client_data=ClientFieldData(prompt_on_new=True, prompt="Enter the bid spread (as decimal, e.g., 0.01 for 1%)"))
    ask_spread: Decimal = Field(Decimal("0.01"), client_data=ClientFieldData(prompt_on_new=True, prompt="Enter the ask spread (as decimal, e.g., 0.01 for 1%)"))
    order_refresh_time: int = Field(30, client_data=ClientFieldData(prompt_on_new=True, prompt="Enter the order refresh time in seconds"))
    price_type: str = Field("mid", client_data=ClientFieldData(prompt_on_new=True, prompt="Enter the price type (mid/best_bid/best_ask)"))


class SomniaPMM(ScriptStrategyBase):
    """
    Simple Pure Market Making strategy for Somnia connector

    This strategy:
    1. Fetches the current market price from orderbook
    2. Places buy orders below the mid price
    3. Places sell orders above the mid price
    4. Refreshes orders periodically
    """

    config: SomniaPMMConfig = SomniaPMMConfig()

    def __init__(self, connectors: Dict[str, ConnectorBase]):
        super().__init__(connectors)
        self.active_orders = {}

    def on_tick(self):
        """
        Called every tick (1 second by default)
        Main strategy logic goes here
        """
        if not self.ready_to_trade:
            return

        # Refresh orders if needed
        if self.should_refresh_orders():
            self.cancel_all_orders()
            self.place_orders()

    def should_refresh_orders(self) -> bool:
        """Check if orders should be refreshed"""
        if not self.active_orders:
            return True

        # Check if it's time to refresh based on config
        return self.current_timestamp % self.config.order_refresh_time == 0

    def place_orders(self):
        """Place buy and sell orders"""
        try:
            # Get market data
            mid_price = self.get_mid_price()
            if mid_price is None:
                self.logger().warning("Cannot get mid price, skipping order placement")
                return

            # Calculate order prices
            bid_price = mid_price * (1 - self.config.bid_spread)
            ask_price = mid_price * (1 + self.config.ask_spread)

            # Check balances before placing orders
            connector = self.connectors[self.config.exchange]

            self.logger().info(f"Mid price: {mid_price}, Bid: {bid_price}, Ask: {ask_price}")

            # Create order candidates
            buy_order = OrderCandidate(
                trading_pair=self.config.trading_pair,
                is_maker=True,
                order_type=OrderType.LIMIT,
                order_side=TradeType.BUY,
                amount=self.config.order_amount,
                price=bid_price
            )

            sell_order = OrderCandidate(
                trading_pair=self.config.trading_pair,
                is_maker=True,
                order_type=OrderType.LIMIT,
                order_side=TradeType.SELL,
                amount=self.config.order_amount,
                price=ask_price
            )

            # Place orders
            self.place_order(connector, buy_order)
            self.place_order(connector, sell_order)

        except Exception as e:
            self.logger().error(f"Error placing orders: {e}")

    def place_order(self, connector: ConnectorBase, order_candidate: OrderCandidate):
        """Place a single order"""
        try:
            if order_candidate.order_side == TradeType.BUY:
                order_id = self.buy(
                    connector_name=self.config.exchange,
                    trading_pair=order_candidate.trading_pair,
                    amount=order_candidate.amount,
                    order_type=order_candidate.order_type,
                    price=order_candidate.price
                )
            else:
                order_id = self.sell(
                    connector_name=self.config.exchange,
                    trading_pair=order_candidate.trading_pair,
                    amount=order_candidate.amount,
                    order_type=order_candidate.order_type,
                    price=order_candidate.price
                )

            if order_id:
                self.active_orders[order_id] = order_candidate
                self.logger().info(f"Placed {order_candidate.order_side.name} order: {order_id}")

        except Exception as e:
            self.logger().error(f"Failed to place {order_candidate.order_side.name} order: {e}")

    def get_mid_price(self) -> Decimal:
        """Get the current mid price from orderbook"""
        try:
            connector = self.connectors[self.config.exchange]

            if self.config.price_type == "mid":
                return connector.get_mid_price(self.config.trading_pair)
            elif self.config.price_type == "best_bid":
                return connector.get_price(self.config.trading_pair, False)  # Best bid
            elif self.config.price_type == "best_ask":
                return connector.get_price(self.config.trading_pair, True)   # Best ask
            else:
                return connector.get_mid_price(self.config.trading_pair)

        except Exception as e:
            self.logger().error(f"Error getting price: {e}")
            return None

    def cancel_all_orders(self):
        """Cancel all active orders"""
        connector = self.connectors[self.config.exchange]
        for order_id in list(self.active_orders.keys()):
            try:
                connector.cancel(self.config.trading_pair, order_id)
                del self.active_orders[order_id]
            except Exception as e:
                self.logger().error(f"Failed to cancel order {order_id}: {e}")

    def did_fill_order(self, event: OrderFilledEvent):
        """Handle order fill events"""
        self.logger().info(f"Order filled: {event.order_id} - {event.trade_type.name} {event.amount} @ {event.price}")

        # Remove from active orders
        if event.order_id in self.active_orders:
            del self.active_orders[event.order_id]

    @property
    def ready_to_trade(self) -> bool:
        """Check if strategy is ready to trade"""
        connector = self.connectors.get(self.config.exchange)
        return (
            connector is not None and
            connector.ready and
            len(connector.get_all_balances()) > 0
        )

    def format_status(self) -> str:
        """Return strategy status for display"""
        lines = []
        lines.append(f"Exchange: {self.config.exchange}")
        lines.append(f"Trading pair: {self.config.trading_pair}")
        lines.append(f"Order amount: {self.config.order_amount}")
        lines.append(f"Spreads: Bid {self.config.bid_spread * 100:.2f}%, Ask {self.config.ask_spread * 100:.2f}%")
        lines.append(f"Active orders: {len(self.active_orders)}")

        if self.ready_to_trade:
            mid_price = self.get_mid_price()
            lines.append(f"Mid price: {mid_price}")

        return "\n".join(lines)
