import logging
import asyncio
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from hummingbot.core.data_type.common import OrderType, TradeType
from hummingbot.core.data_type.order_candidate import OrderCandidate
from hummingbot.core.event.events import OrderFilledEvent
from hummingbot.strategy.script_strategy_base import ScriptStrategyBase


class SomniaTriangularArbitrage(ScriptStrategyBase):
    """
    Somnia Triangular Arbitrage Strategy
    
    This strategy performs triangular arbitrage across three trading pairs on Somnia DEX:
    1. STT/USDC
    2. WBTC/USDC  
    3. SOL/USDC
    
    It monitors price relationships between these three assets and executes triangular arbitrage
    when profitable opportunities arise. Since all pairs share USDC as the quote asset,
    we can easily calculate cross-rates and identify arbitrage opportunities.
    """
    
    # Configuration parameters
    order_amount_usd = Decimal("100.0")  # USD value to trade per opportunity
    min_profitability = Decimal("0.005")  # 0.5% minimum profit threshold
    
    # Trading pairs on Somnia
    stt_usdc_pair = "STT-USDC"
    wbtc_usdc_pair = "WBTC-USDC"
    sol_usdc_pair = "SOL-USDC"
    
    exchange = "somnia"  # Using Somnia DEX for all pairs
    
    # Define markets - all three pairs on the same exchange
    markets = {exchange: {stt_usdc_pair, wbtc_usdc_pair, sol_usdc_pair}}
    
    def __init__(self, connectors, config):
        super().__init__(connectors)
        
        # State tracking
        self.last_arbitrage_time = 0
        self.cooldown_period = 30  # seconds between arbitrage attempts
        self.active_orders = []
        
        # Price cache for analysis
        self.price_cache = {}
        self.last_price_update = 0
        
        self.logger().info("Somnia Triangular Arbitrage Strategy initialized")
        self.logger().info(f"Monitoring pairs: {self.stt_usdc_pair}, {self.wbtc_usdc_pair}, {self.sol_usdc_pair}")

    def on_tick(self):
        """
        Main strategy loop executed on each tick.
        """
        try:
            # Check cooldown period
            current_time = self.current_timestamp
            if current_time - self.last_arbitrage_time < self.cooldown_period:
                return
                
            # Get current prices for all pairs
            prices_data = self.get_all_pair_prices()
            
            if prices_data is None:
                return
                
            # Analyze triangular arbitrage opportunities
            arbitrage_opportunities = self.analyze_triangular_arbitrage(prices_data)
            
            if arbitrage_opportunities:
                best_opportunity = max(arbitrage_opportunities, key=lambda x: x['profit_pct'])
                
                if best_opportunity['profit_pct'] > self.min_profitability:
                    self.logger().info(f"Triangular arbitrage opportunity found: {best_opportunity['profit_pct']:.4%} profit")
                    self.execute_triangular_arbitrage(best_opportunity)
                    self.last_arbitrage_time = current_time
                    
        except Exception as e:
            self.logger().error(f"Error in on_tick: {e}")

    def get_all_pair_prices(self) -> Optional[Dict[str, Dict[str, Decimal]]]:
        """
        Get current bid/ask prices for all three trading pairs.
        """
        try:
            connector = self.connectors[self.exchange]
            
            # Get price data for all pairs
            pairs_data = {}
            
            for pair in [self.stt_usdc_pair, self.wbtc_usdc_pair, self.sol_usdc_pair]:
                # Use smaller amounts for price discovery to get better fills
                test_amount = self.get_test_amount_for_pair(pair)
                
                bid_price = connector.get_vwap_for_volume(pair, False, test_amount)
                ask_price = connector.get_vwap_for_volume(pair, True, test_amount)
                
                if bid_price is None or ask_price is None or bid_price.result_price is None or ask_price.result_price is None:
                    self.logger().warning(f"Failed to get price data for {pair}")
                    return None
                    
                pairs_data[pair] = {
                    "bid": bid_price.result_price,
                    "ask": ask_price.result_price,
                    "mid": (bid_price.result_price + ask_price.result_price) / 2
                }
            
            self.price_cache = pairs_data
            self.last_price_update = self.current_timestamp
            return pairs_data
            
        except Exception as e:
            self.logger().error(f"Error getting pair prices: {e}")
            return None

    def get_test_amount_for_pair(self, pair: str) -> Decimal:
        """
        Get appropriate test amount for price discovery based on the pair.
        """
        if "WBTC" in pair:
            return Decimal("0.001")  # Small amount for WBTC due to high value
        elif "SOL" in pair:
            return Decimal("1.0")    # Moderate amount for SOL
        else:  # STT pairs
            return Decimal("10.0")   # Larger amount for STT

    def analyze_triangular_arbitrage(self, prices_data: Dict[str, Dict[str, Decimal]]) -> List[Dict]:
        """
        Analyze all possible triangular arbitrage opportunities.
        
        With STT, WBTC, SOL all paired with USDC, we can perform triangular arbitrage by:
        1. Converting between any two assets through USDC
        2. Comparing cross-rates with external market rates
        3. Finding discrepancies in relative pricing
        """
        opportunities = []
        
        try:
            stt_prices = prices_data[self.stt_usdc_pair]
            wbtc_prices = prices_data[self.wbtc_usdc_pair]
            sol_prices = prices_data[self.sol_usdc_pair]
            
            # Calculate all possible arbitrage paths
            
            # Path 1: STT -> WBTC -> SOL -> STT (via USDC)
            opp1 = self.calculate_arbitrage_path(
                "STT->WBTC->SOL",
                [(self.stt_usdc_pair, "sell", stt_prices["bid"]),    # STT to USDC
                 (self.wbtc_usdc_pair, "buy", wbtc_prices["ask"]),   # USDC to WBTC  
                 (self.sol_usdc_pair, "buy", sol_prices["ask"]),     # USDC to SOL (hypothetical)
                 (self.stt_usdc_pair, "buy", stt_prices["ask"])]     # USDC to STT
            )
            if opp1:
                opportunities.append(opp1)
                
            # Path 2: STT -> SOL -> WBTC -> STT (via USDC)
            opp2 = self.calculate_arbitrage_path(
                "STT->SOL->WBTC",
                [(self.stt_usdc_pair, "sell", stt_prices["bid"]),   # STT to USDC
                 (self.sol_usdc_pair, "buy", sol_prices["ask"]),    # USDC to SOL
                 (self.wbtc_usdc_pair, "buy", wbtc_prices["ask"]),  # USDC to WBTC (hypothetical)
                 (self.stt_usdc_pair, "buy", stt_prices["ask"])]    # USDC to STT
            )
            if opp2:
                opportunities.append(opp2)
                
            # Simplified two-step arbitrage opportunities
            
            # STT vs WBTC relative value arbitrage
            stt_wbtc_opp = self.calculate_cross_pair_arbitrage("STT-WBTC", stt_prices, wbtc_prices)
            if stt_wbtc_opp:
                opportunities.append(stt_wbtc_opp)
                
            # STT vs SOL relative value arbitrage  
            stt_sol_opp = self.calculate_cross_pair_arbitrage("STT-SOL", stt_prices, sol_prices)
            if stt_sol_opp:
                opportunities.append(stt_sol_opp)
                
            # WBTC vs SOL relative value arbitrage
            wbtc_sol_opp = self.calculate_cross_pair_arbitrage("WBTC-SOL", wbtc_prices, sol_prices)
            if wbtc_sol_opp:
                opportunities.append(wbtc_sol_opp)
                
        except Exception as e:
            self.logger().error(f"Error analyzing triangular arbitrage: {e}")
            
        return opportunities

    def calculate_cross_pair_arbitrage(self, pair_name: str, prices1: Dict, prices2: Dict) -> Optional[Dict]:
        """
        Calculate arbitrage opportunity between two assets via USDC.
        This is simpler than full triangular arbitrage but still profitable.
        """
        try:
            # Example: If STT is cheap in USDC terms and WBTC is expensive,
            # we could buy STT, sell WBTC, and capture the relative value difference
            
            # For simplicity, we'll focus on whether the spread between the pairs
            # creates an arbitrage opportunity when trading equivalent USD amounts
            
            spread1 = (prices1["ask"] - prices1["bid"]) / prices1["mid"]
            spread2 = (prices2["ask"] - prices2["bid"]) / prices2["mid"]
            
            # Look for significant spread differences that could indicate opportunity
            spread_diff = abs(spread1 - spread2)
            
            if spread_diff > self.min_profitability:
                return {
                    "type": "cross_pair",
                    "pair_name": pair_name,
                    "profit_pct": spread_diff,
                    "description": f"Cross-pair arbitrage between {pair_name.split('-')[0]} and {pair_name.split('-')[1]}",
                    "execution_plan": self.create_cross_pair_execution_plan(pair_name, prices1, prices2, spread_diff > 0)
                }
                
        except Exception as e:
            self.logger().error(f"Error calculating cross-pair arbitrage for {pair_name}: {e}")
            
        return None

    def calculate_arbitrage_path(self, path_name: str, steps: List[Tuple]) -> Optional[Dict]:
        """
        Calculate the profitability of a multi-step arbitrage path.
        This is a simplified calculation - in practice, you'd need more sophisticated modeling.
        """
        try:
            # For now, return None as full triangular arbitrage requires more complex calculation
            # Focus on the simpler cross-pair arbitrage for initial implementation
            return None
            
        except Exception as e:
            self.logger().error(f"Error calculating arbitrage path {path_name}: {e}")
            return None

    def create_cross_pair_execution_plan(self, pair_name: str, prices1: Dict, prices2: Dict, buy_first: bool) -> List[Dict]:
        """
        Create execution plan for cross-pair arbitrage.
        """
        plan = []
        
        try:
            # Determine which pairs to trade
            asset1, asset2 = pair_name.split('-')
            pair1 = f"{asset1}-USDC"
            pair2 = f"{asset2}-USDC"
            
            # Calculate order amounts based on USD value
            usd_amount = self.order_amount_usd
            
            if buy_first:
                # Buy asset1, sell asset2
                amount1 = usd_amount / prices1["ask"]  # Buy asset1 with USD
                amount2 = usd_amount / prices2["bid"]  # Sell asset2 for USD
                
                plan = [
                    {"pair": pair1, "side": "buy", "amount": amount1, "price": prices1["ask"]},
                    {"pair": pair2, "side": "sell", "amount": amount2, "price": prices2["bid"]}
                ]
            else:
                # Sell asset1, buy asset2  
                amount1 = usd_amount / prices1["bid"]  # Sell asset1 for USD
                amount2 = usd_amount / prices2["ask"]  # Buy asset2 with USD
                
                plan = [
                    {"pair": pair1, "side": "sell", "amount": amount1, "price": prices1["bid"]},
                    {"pair": pair2, "side": "buy", "amount": amount2, "price": prices2["ask"]}
                ]
                
        except Exception as e:
            self.logger().error(f"Error creating execution plan: {e}")
            
        return plan

    def execute_triangular_arbitrage(self, opportunity: Dict):
        """
        Execute the triangular arbitrage opportunity.
        """
        try:
            execution_plan = opportunity.get("execution_plan", [])
            
            if not execution_plan:
                self.logger().warning("No execution plan found for arbitrage opportunity")
                return
                
            self.logger().info(f"Executing {opportunity['type']} arbitrage: {opportunity['description']}")
            
            # Execute orders according to the plan
            for step in execution_plan:
                order_candidate = OrderCandidate(
                    trading_pair=step["pair"],
                    is_maker=False,
                    order_type=OrderType.MARKET,
                    order_side=TradeType.BUY if step["side"] == "buy" else TradeType.SELL,
                    amount=step["amount"],
                    price=step["price"]
                )
                
                # Adjust order to budget
                adjusted_order = self.connectors[self.exchange].budget_checker.adjust_candidate(order_candidate, all_or_none=True)
                
                if adjusted_order.amount > 0:
                    self.place_order(self.exchange, adjusted_order)
                    self.active_orders.append(adjusted_order)
                else:
                    self.logger().warning(f"Insufficient balance for {step['pair']} {step['side']} order")
                    
        except Exception as e:
            self.logger().error(f"Error executing triangular arbitrage: {e}")

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
                        
            self.logger().info(f"Placed {order.order_side.name} order: {order.amount} {order.trading_pair} at {order.price}")
            
        except Exception as e:
            self.logger().error(f"Error placing {order.order_side} order: {e}")

    def format_status(self) -> str:
        """
        Format and return strategy status information.
        """
        try:
            lines = []
            lines.append("\\n========== Somnia Triangular Arbitrage Strategy ==========")
            lines.append(f"Exchange: {self.exchange}")
            lines.append(f"Trading Pairs: {self.stt_usdc_pair}, {self.wbtc_usdc_pair}, {self.sol_usdc_pair}")
            lines.append(f"Order Amount (USD): {self.order_amount_usd}")
            lines.append(f"Min Profitability: {self.min_profitability:.2%}")
            lines.append(f"Cooldown Period: {self.cooldown_period}s")
            lines.append("")
            
            # Current prices
            if self.price_cache:
                lines.append("Current Prices:")
                for pair, prices in self.price_cache.items():
                    lines.append(f"  {pair}: Bid {prices['bid']:.6f}, Ask {prices['ask']:.6f}, Mid {prices['mid']:.6f}")
                lines.append("")
                
                # Quick arbitrage analysis
                if len(self.price_cache) == 3:
                    opportunities = self.analyze_triangular_arbitrage(self.price_cache)
                    
                    lines.append(f"Arbitrage Opportunities Found: {len(opportunities)}")
                    for opp in opportunities[:3]:  # Show top 3
                        lines.append(f"  {opp['description']}: {opp['profit_pct']:.4%} profit")
                        
                    if opportunities:
                        best_opp = max(opportunities, key=lambda x: x['profit_pct'])
                        lines.append(f"Best Opportunity: {best_opp['profit_pct']:.4%} ({'EXECUTABLE' if best_opp['profit_pct'] > self.min_profitability else 'BELOW THRESHOLD'})")
                    else:
                        lines.append("No profitable opportunities currently available")
            else:
                lines.append("Waiting for price data...")
                
            lines.append("")
            lines.append(f"Active Orders: {len(self.active_orders)}")
            
            # Cooldown status
            time_since_last = self.current_timestamp - self.last_arbitrage_time
            if time_since_last < self.cooldown_period:
                lines.append(f"Cooldown: {self.cooldown_period - time_since_last:.1f}s remaining")
            else:
                lines.append("Ready for arbitrage")
                
            return "\\n".join(lines)
            
        except Exception as e:
            return f"Status Error: {e}"

    def did_fill_order(self, event: OrderFilledEvent):
        """
        Handle order fill events.
        """
        msg = f"Arbitrage order filled: {event.trade_type.name} {round(event.amount, 6)} {event.trading_pair} at {round(event.price, 6)}"
        self.log_with_clock(logging.INFO, msg)
        self.notify_hb_app_with_timestamp(msg)
        
        # Remove from active orders
        self.active_orders = [order for order in self.active_orders 
                             if not (order.trading_pair == event.trading_pair and 
                                   abs(float(order.amount) - float(event.amount)) < 0.000001)]
