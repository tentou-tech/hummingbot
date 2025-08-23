import logging
from decimal import Decimal
from typing import Any, Dict

import pandas as pd

from hummingbot.core.data_type.common import OrderType, TradeType
from hummingbot.core.data_type.order_candidate import OrderCandidate
from hummingbot.core.event.events import OrderFilledEvent
from hummingbot.strategy.script_strategy_base import ScriptStrategyBase


class STTAmmArbitrage(ScriptStrategyBase):
    """
    STT AMM Arbitrage Strategy
    
    This strategy performs arbitrage between two STT trading pairs on the Somnia DEX:
    1. STT/USDC
    2. STT/WBTC
    
    It monitors price differences between these pairs and executes arbitrage trades when profitable.
    The strategy calculates cross-rate arbitrage opportunities by comparing STT prices in both USDC and WBTC terms.
    """
    
    # Configuration parameters
    order_amount = Decimal("10.0")  # Amount of STT to trade
    min_profitability = Decimal("0.005")  # 0.5% minimum profit threshold
    base = "STT"
    quote_1 = "USDC"  # Primary quote asset
    quote_2 = "WBTC"  # Secondary quote asset
    
    trading_pair_1 = f"{base}-{quote_1}"  # STT-USDC
    trading_pair_2 = f"{base}-{quote_2}"  # STT-WBTC
    
    exchange = "standard-testnet"  # Using Somnia DEX for both pairs
    
    # Define markets - both pairs on the same exchange
    markets = {exchange: {trading_pair_1, trading_pair_2}}
    
    def on_tick(self):
        """
        Main strategy loop executed on each tick.
        """
        try:
            # Get current prices for both trading pairs
            prices_data = self.get_cross_pair_prices()
            
            if prices_data is None:
                return
                
            # Check for arbitrage opportunities
            proposal = self.check_cross_pair_arbitrage(prices_data)
            
            if len(proposal) > 0:
                self.logger().info(f"Arbitrage opportunity found: {proposal}")
                proposal_adjusted = self.adjust_proposal_to_budget(proposal)
                self.place_orders(proposal_adjusted)
                
        except Exception as e:
            self.logger().error(f"Error in on_tick: {e}")

    def get_cross_pair_prices(self) -> Dict[str, Any]:
        """
        Get current bid/ask prices for both STT trading pairs.
        Returns price data needed for cross-pair arbitrage analysis.
        """
        try:
            connector = self.connectors[self.exchange]
            
            # Get VWAP prices for STT-USDC pair
            stt_usdc_bid = connector.get_vwap_for_volume(self.trading_pair_1, False, self.order_amount)
            stt_usdc_ask = connector.get_vwap_for_volume(self.trading_pair_1, True, self.order_amount)
            
            # Get VWAP prices for STT-WBTC pair  
            stt_wbtc_bid = connector.get_vwap_for_volume(self.trading_pair_2, False, self.order_amount)
            stt_wbtc_ask = connector.get_vwap_for_volume(self.trading_pair_2, True, self.order_amount)
            
            # Check if all price queries were successful
            if any(price is None or price.result_price is None for price in [stt_usdc_bid, stt_usdc_ask, stt_wbtc_bid, stt_wbtc_ask]):
                self.logger().warning("Failed to get complete price data")
                return None
                
            return {
                "stt_usdc": {
                    "bid": stt_usdc_bid.result_price,
                    "ask": stt_usdc_ask.result_price
                },
                "stt_wbtc": {
                    "bid": stt_wbtc_bid.result_price,
                    "ask": stt_wbtc_ask.result_price
                }
            }
            
        except Exception as e:
            self.logger().error(f"Error getting cross pair prices: {e}")
            return None

    def get_usdc_wbtc_rate(self) -> Decimal:
        """
        Get the current USDC/WBTC exchange rate.
        This could be from an oracle, or estimated from market data.
        For now, using a rough approximation - in production this should use a rate oracle.
        """
        # Approximate WBTC price in USDC terms (this should be from a rate oracle in production)
        # WBTC ≈ $65,000 USDC (this is a placeholder - should be dynamic)
        return Decimal("65000")

    def check_cross_pair_arbitrage(self, prices_data: Dict[str, Any]) -> Dict[str, OrderCandidate]:
        """
        Check for arbitrage opportunities between STT-USDC and STT-WBTC pairs.
        
        Strategy:
        1. Calculate implied STT price in USDC terms from both pairs
        2. If prices differ by more than min_profitability, execute arbitrage
        3. Buy STT on the cheaper market, sell on the expensive market
        """
        proposal = {}
        
        try:
            stt_usdc_prices = prices_data["stt_usdc"]
            stt_wbtc_prices = prices_data["stt_wbtc"]
            
            # Get USDC/WBTC conversion rate
            usdc_wbtc_rate = self.get_usdc_wbtc_rate()
            
            # Convert STT-WBTC prices to USDC terms for comparison
            stt_from_wbtc_bid_usdc = stt_wbtc_prices["bid"] * usdc_wbtc_rate  # STT price via WBTC->USDC
            stt_from_wbtc_ask_usdc = stt_wbtc_prices["ask"] * usdc_wbtc_rate
            
            # Calculate potential arbitrage profits
            # Scenario 1: Buy STT with USDC, sell STT for WBTC (then convert WBTC to USDC)
            profit_1 = stt_from_wbtc_bid_usdc - stt_usdc_prices["ask"]
            profit_1_pct = profit_1 / stt_usdc_prices["ask"] if stt_usdc_prices["ask"] > 0 else Decimal("0")
            
            # Scenario 2: Buy STT with WBTC, sell STT for USDC
            profit_2 = stt_usdc_prices["bid"] - stt_from_wbtc_ask_usdc
            profit_2_pct = profit_2 / stt_from_wbtc_ask_usdc if stt_from_wbtc_ask_usdc > 0 else Decimal("0")
            
            self.logger().info(f"Cross-pair analysis: USDC path profit: {profit_1_pct:.4%}, WBTC path profit: {profit_2_pct:.4%}")
            
            # Execute arbitrage if profitable
            if profit_1_pct > self.min_profitability:
                # Buy STT with USDC, sell STT for WBTC
                self.logger().info(f"Executing arbitrage: Buy STT-USDC, Sell STT-WBTC (profit: {profit_1_pct:.4%})")
                
                proposal[f"{self.exchange}_usdc"] = OrderCandidate(
                    trading_pair=self.trading_pair_1,
                    is_maker=False,
                    order_type=OrderType.MARKET,
                    order_side=TradeType.BUY,
                    amount=self.order_amount,
                    price=stt_usdc_prices["ask"]
                )
                
                proposal[f"{self.exchange}_wbtc"] = OrderCandidate(
                    trading_pair=self.trading_pair_2,
                    is_maker=False,
                    order_type=OrderType.MARKET,
                    order_side=TradeType.SELL,
                    amount=self.order_amount,
                    price=stt_wbtc_prices["bid"]
                )
                
            elif profit_2_pct > self.min_profitability:
                # Buy STT with WBTC, sell STT for USDC
                self.logger().info(f"Executing arbitrage: Buy STT-WBTC, Sell STT-USDC (profit: {profit_2_pct:.4%})")
                
                proposal[f"{self.exchange}_wbtc"] = OrderCandidate(
                    trading_pair=self.trading_pair_2,
                    is_maker=False,
                    order_type=OrderType.MARKET,
                    order_side=TradeType.BUY,
                    amount=self.order_amount,
                    price=stt_wbtc_prices["ask"]
                )
                
                proposal[f"{self.exchange}_usdc"] = OrderCandidate(
                    trading_pair=self.trading_pair_1,
                    is_maker=False,
                    order_type=OrderType.MARKET,
                    order_side=TradeType.SELL,
                    amount=self.order_amount,
                    price=stt_usdc_prices["bid"]
                )
                
        except Exception as e:
            self.logger().error(f"Error in arbitrage calculation: {e}")
            
        return proposal

    def adjust_proposal_to_budget(self, proposal: Dict[str, OrderCandidate]) -> Dict[str, OrderCandidate]:
        """
        Adjust order sizes based on available budget.
        """
        try:
            for connector_key, order in proposal.items():
                # Extract the actual connector name (remove suffix like '_usdc' or '_wbtc')
                connector_name = self.exchange
                proposal[connector_key] = self.connectors[connector_name].budget_checker.adjust_candidate(order, all_or_none=True)
            return proposal
        except Exception as e:
            self.logger().error(f"Error adjusting proposal to budget: {e}")
            return {}

    def place_orders(self, proposal: Dict[str, OrderCandidate]) -> None:
        """
        Place the arbitrage orders.
        """
        try:
            for connector_key, order in proposal.items():
                self.place_order(self.exchange, order)
        except Exception as e:
            self.logger().error(f"Error placing orders: {e}")

    def place_order(self, connector_name: str, order: OrderCandidate):
        """
        Place a single order on the specified connector.
        """
        try:
            if order.order_side == TradeType.SELL:
                self.sell(connector_name=connector_name, trading_pair=order.trading_pair, 
                         amount=order.amount, order_type=order.order_type, price=order.price)
            elif order.order_side == TradeType.BUY:
                self.buy(connector_name=connector_name, trading_pair=order.trading_pair, 
                        amount=order.amount, order_type=order.order_type, price=order.price)
        except Exception as e:
            self.logger().error(f"Error placing {order.order_side} order: {e}")

    def format_status(self) -> str:
        """
        Format and return strategy status information.
        """
        try:
            prices_data = self.get_cross_pair_prices()
            
            if prices_data is None:
                return "Status: Unable to fetch price data"
                
            lines = []
            lines.append("\\n========== STT AMM Arbitrage Strategy ==========")
            lines.append(f"Exchange: {self.exchange}")
            lines.append(f"Trading Pairs: {self.trading_pair_1}, {self.trading_pair_2}")
            lines.append(f"Order Amount: {self.order_amount} {self.base}")
            lines.append(f"Min Profitability: {self.min_profitability:.2%}")
            lines.append("")
            
            # Current prices
            stt_usdc = prices_data["stt_usdc"]
            stt_wbtc = prices_data["stt_wbtc"]
            
            lines.append("Current Prices:")
            lines.append(f"  {self.trading_pair_1}: Bid {stt_usdc['bid']:.6f}, Ask {stt_usdc['ask']:.6f}")
            lines.append(f"  {self.trading_pair_2}: Bid {stt_wbtc['bid']:.8f}, Ask {stt_wbtc['ask']:.8f}")
            lines.append("")
            
            # Cross-rate analysis
            usdc_wbtc_rate = self.get_usdc_wbtc_rate()
            stt_via_wbtc_usdc = stt_wbtc["bid"] * usdc_wbtc_rate
            
            lines.append("Cross-Rate Analysis:")
            lines.append(f"  USDC/WBTC Rate: {usdc_wbtc_rate:.0f}")
            lines.append(f"  STT via USDC: {stt_usdc['bid']:.6f} USDC")
            lines.append(f"  STT via WBTC: {stt_via_wbtc_usdc:.6f} USDC (converted)")
            
            price_diff = abs(stt_usdc['bid'] - stt_via_wbtc_usdc)
            price_diff_pct = price_diff / stt_usdc['bid'] if stt_usdc['bid'] > 0 else Decimal("0")
            
            lines.append(f"  Price Difference: {price_diff_pct:.4%}")
            lines.append(f"  Arbitrage Opportunity: {'YES' if price_diff_pct > self.min_profitability else 'NO'}")
            
            return "\\n".join(lines)
            
        except Exception as e:
            return f"Status Error: {e}"

    def did_fill_order(self, event: OrderFilledEvent):
        """
        Handle order fill events.
        """
        msg = f"Order filled: {event.trade_type.name} {round(event.amount, 4)} {event.trading_pair} at {round(event.price, 6)}"
        self.log_with_clock(logging.INFO, msg)
        self.notify_hb_app_with_timestamp(msg)
