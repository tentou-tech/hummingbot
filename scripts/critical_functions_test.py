#!/usr/bin/env python3
"""
🧪 COMPREHENSIVE SOMNIA CONNECTOR TESTING SUITE

This script performs thorough testing of the Somnia connector's critical functions:
- Network connectivity and initialization
- Balance checking and management
- Price quoting and market data
- Order placement and management
- Fee calculations
- Error handling and recovery

⚠️  WARNING: This uses REAL tokens on Somnia testnet!
"""

import asyncio
import logging
import os
import sys
from decimal import Decimal
from typing import Any, Dict

from dotenv import load_dotenv

from hummingbot.client.config.client_config_map import ClientConfigMap
from hummingbot.client.config.config_helpers import ClientConfigAdapter
from hummingbot.connector.gateway.somnia.somnia_connector import SomniaConnector
from hummingbot.core.data_type.common import OrderType, TradeType

# Load environment variables from .env file
load_dotenv()

# Add hummingbot to path
sys.path.append('/home/thien/hummingbot')

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# 🔧 TRADING PAIR CONFIGURATION
# Change these values to test different pairs
TEST_CONFIG = {
    # Trading pair to test
    "trading_pair": "STT-USDC",

    # Base and quote currency info
    "base_currency": "STT",
    "quote_currency": "USDC",
    "base_token_address": "0x4A3BC48C156384f9564Fd65A53a2f3D534D8f2b7",
    "quote_token_address": "0x0ED782B8079529f7385c3eDA9fAf1EaA0DbC6a17",

    # Wallet address (should match private key in .env)
    "wallet_address": "0xa3d3bf1DCCB0C53887fF94822BF197fB7Eb961D8",

    # Test amounts for orders
    "test_amount": Decimal("0.1"),
    "test_price": Decimal("1.0"),
    "low_price": Decimal("0.1"),  # For safe order placement

    # Network configuration
    "chain": "somnia",
    "network": "testnet",
    "connector_name": "somnia"
}

# 📝 ALTERNATIVE PAIR CONFIGURATIONS (uncomment to use)
# TEST_CONFIG_BTC_USDC = {
#     "trading_pair": "BTC-USDC",
#     "base_currency": "BTC",
#     "quote_currency": "USDC",
#     "base_token_address": "0x...",  # Add BTC token address
#     "quote_token_address": "0x0ED782B8079529f7385c3eDA9fAf1EaA0DbC6a17",
#     "wallet_address": "0xa3d3bf1DCCB0C53887fF94822BF197fB7Eb961D8",
#     "test_amount": Decimal("0.001"),
#     "test_price": Decimal("50000"),
#     "low_price": Decimal("10000"),
#     "chain": "somnia",
#     "network": "testnet",
#     "connector_name": "somnia"
# }

# To switch pairs, uncomment this line:
# TEST_CONFIG = TEST_CONFIG_BTC_USDC


def create_test_config(
    trading_pair: str,
    base_currency: str,
    quote_currency: str,
    base_token_address: str,
    quote_token_address: str,
    wallet_address: str = "0xa3d3bf1DCCB0C53887fF94822BF197fB7Eb961D8",
    test_amount: str = "0.1",
    test_price: str = "1.0",
    low_price: str = "0.1"
) -> Dict[str, Any]:
    """
    Helper function to create test configuration for different trading pairs

    Args:
        trading_pair: e.g., "BTC-USDC", "ETH-USDC"
        base_currency: e.g., "BTC", "ETH"
        quote_currency: e.g., "USDC", "USDT"
        base_token_address: Contract address for base token
        quote_token_address: Contract address for quote token
        wallet_address: Your wallet address (should match private key)
        test_amount: Amount to use in tests
        test_price: Price to use in fee calculations
        low_price: Low price for safe order placement

    Returns:
        Configuration dictionary
    """
    return {
        "trading_pair": trading_pair,
        "base_currency": base_currency,
        "quote_currency": quote_currency,
        "base_token_address": base_token_address,
        "quote_token_address": quote_token_address,
        "wallet_address": wallet_address,
        "test_amount": Decimal(test_amount),
        "test_price": Decimal(test_price),
        "low_price": Decimal(low_price),
        "chain": "somnia",
        "network": "testnet",
        "connector_name": "somnia"
    }

# 🚀 QUICK CONFIGURATION EXAMPLES:
# Uncomment any of these to switch test pairs instantly:

# TEST_CONFIG = create_test_config(
#     trading_pair="BTC-USDC",
#     base_currency="BTC",
#     quote_currency="USDC",
#     base_token_address="0x...",  # Add actual BTC token address
#     quote_token_address="0x0ED782B8079529f7385c3eDA9fAf1EaA0DbC6a17",
#     test_amount="0.001",
#     test_price="50000",
#     low_price="10000"
# )

# TEST_CONFIG = create_test_config(
#     trading_pair="ETH-USDC",
#     base_currency="ETH",
#     quote_currency="USDC",
#     base_token_address="0x...",  # Add actual ETH token address
#     quote_token_address="0x0ED782B8079529f7385c3eDA9fAf1EaA0DbC6a17",
#     test_amount="0.01",
#     test_price="3000",
#     low_price="1000"
# )


class CriticalFunctionsTest:
    def __init__(self):
        self.connector = None
        self.test_results = {}

    async def setup_connector(self):
        """Initialize the Somnia connector"""
        logger.info("🔧 Setting up Somnia connector...")
        logger.info(f"📊 Testing pair: {TEST_CONFIG['trading_pair']}")
        logger.info(f"💰 Base: {TEST_CONFIG['base_currency']} ({TEST_CONFIG['base_token_address']})")
        logger.info(f"💰 Quote: {TEST_CONFIG['quote_currency']} ({TEST_CONFIG['quote_token_address']})")

        # Verify private key is available
        private_key = os.getenv("SOMNIA_PRIVATE_KEY")
        if not private_key:
            logger.error("❌ SOMNIA_PRIVATE_KEY not found in .env file!")
            logger.error("   Please ensure .env file contains SOMNIA_PRIVATE_KEY=0x...")
            return False
        else:
            logger.info("✅ Private key loaded from .env file")
            logger.info(f"   Key preview: {private_key[:6]}...{private_key[-4:]}")

        try:
            # Create client config
            client_config = ClientConfigMap()
            client_config_adapter = ClientConfigAdapter(client_config)

            # Initialize connector with configurable trading pairs
            self.connector = SomniaConnector(
                client_config_map=client_config_adapter,
                connector_name=TEST_CONFIG["connector_name"],
                chain=TEST_CONFIG["chain"],
                network=TEST_CONFIG["network"],
                address=TEST_CONFIG["wallet_address"],
                trading_pairs=[TEST_CONFIG["trading_pair"]],
                trading_required=True
            )

            # Start the connector
            await self.connector.start_network()

            # Verify we're using the correct wallet address
            connector_address = self.connector._standard_client.address
            expected_address = TEST_CONFIG["wallet_address"]

            if connector_address.lower() == expected_address.lower():
                logger.info(f"✅ Wallet address verified: {connector_address}")
            else:
                logger.warning("⚠️  Wallet address mismatch!")
                logger.warning(f"   Expected: {expected_address}")
                logger.warning(f"   Got: {connector_address}")

            logger.info("✅ Connector setup complete")
            return True

        except Exception as e:
            logger.error(f"❌ Connector setup failed: {e}")
            return False

    async def test_price_quotes(self) -> Dict[str, Any]:
        """Test price quote functionality"""
        logger.info("📊 Testing price quote functions...")
        logger.info(f"   🎯 Target Pair: {TEST_CONFIG['trading_pair']}")
        logger.info(f"   📏 Test Amount: {TEST_CONFIG['test_amount']}")

        result = {
            "test_name": "Price Quotes",
            "status": "UNKNOWN",
            "details": {},
            "errors": []
        }

        try:
            # Test get_order_price_quote
            logger.info("🔍 Testing get_order_price_quote...")
            logger.info(f"   📈 Requesting BUY price for {TEST_CONFIG['test_amount']} {TEST_CONFIG['base_currency']}")

            buy_price = await self.connector.get_order_price_quote(
                trading_pair=TEST_CONFIG["trading_pair"],
                is_buy=True,
                amount=TEST_CONFIG["test_amount"]
            )
            logger.info(f"   ✅ Buy price quote received: {buy_price}")
            logger.info(f"   💰 Cost: {float(buy_price) * float(TEST_CONFIG['test_amount']):.6f} {TEST_CONFIG['quote_currency']}")
            result["details"]["buy_price"] = str(buy_price)
            result["details"]["buy_cost"] = str(float(buy_price) * float(TEST_CONFIG['test_amount']))

            logger.info(f"   📉 Requesting SELL price for {TEST_CONFIG['test_amount']} {TEST_CONFIG['base_currency']}")
            sell_price = await self.connector.get_order_price_quote(
                trading_pair=TEST_CONFIG["trading_pair"],
                is_buy=False,
                amount=TEST_CONFIG["test_amount"]
            )
            logger.info(f"   ✅ Sell price quote received: {sell_price}")
            logger.info(f"   💰 Revenue: {float(sell_price) * float(TEST_CONFIG['test_amount']):.6f} {TEST_CONFIG['quote_currency']}")
            result["details"]["sell_price"] = str(sell_price)
            result["details"]["sell_revenue"] = str(float(sell_price) * float(TEST_CONFIG['test_amount']))

            # Calculate spread if both prices available
            if buy_price and sell_price and float(buy_price) > 0 and float(sell_price) > 0:
                spread = abs(float(buy_price) - float(sell_price))
                spread_pct = (spread / float(buy_price)) * 100
                logger.info(f"   📊 Price Spread: {spread:.6f} ({spread_pct:.2f}%)")
                result["details"]["spread"] = str(spread)
                result["details"]["spread_pct"] = f"{spread_pct:.2f}%"

            # Test get_mid_price
            logger.info("🔍 Testing get_mid_price...")
            mid_price = self.connector.get_mid_price(TEST_CONFIG["trading_pair"])
            logger.info(f"   ✅ Mid price: {mid_price}")
            result["details"]["mid_price"] = str(mid_price) if mid_price else "None"

            if mid_price and float(mid_price) > 0:
                logger.info(f"   💱 Mid price for {TEST_CONFIG['test_amount']} {TEST_CONFIG['base_currency']}: {float(mid_price) * float(TEST_CONFIG['test_amount']):.6f} {TEST_CONFIG['quote_currency']}")

            result["status"] = "PASSED"
            logger.info("✅ Price quotes test PASSED")

        except Exception as e:
            logger.error(f"❌ Price quotes test failed: {e}")
            logger.error(f"   🔍 Exception type: {type(e).__name__}")
            logger.error(f"   📝 Exception details: {str(e)}")
            result["status"] = "FAILED"
            result["errors"].append(str(e))

        return result

    async def test_fee_calculation(self) -> Dict[str, Any]:
        """Test fee calculation"""
        logger.info("💰 Testing fee calculation...")
        logger.info(f"   🎯 Pair: {TEST_CONFIG['base_currency']}-{TEST_CONFIG['quote_currency']}")
        logger.info(f"   📏 Amount: {TEST_CONFIG['test_amount']} {TEST_CONFIG['base_currency']}")
        logger.info(f"   💵 Price: {TEST_CONFIG['test_price']} {TEST_CONFIG['quote_currency']}")

        result = {
            "test_name": "Fee Calculation",
            "status": "UNKNOWN",
            "details": {},
            "errors": []
        }

        try:
            # Test buy order fee
            logger.info("🔍 Testing BUY order fee calculation...")
            buy_fee = self.connector.get_fee(
                base_currency=TEST_CONFIG["base_currency"],
                quote_currency=TEST_CONFIG["quote_currency"],
                order_type=OrderType.LIMIT,
                order_side=TradeType.BUY,
                amount=TEST_CONFIG["test_amount"],
                price=TEST_CONFIG["test_price"]
            )
            logger.info(f"   ✅ Buy order fee structure: {buy_fee}")

            # Extract fee details
            if hasattr(buy_fee, 'flat_fees'):
                logger.info(f"   📊 Buy flat fees: {buy_fee.flat_fees}")
                result["details"]["buy_flat_fees"] = str(buy_fee.flat_fees)
            if hasattr(buy_fee, 'percent'):
                logger.info(f"   📊 Buy fee percentage: {buy_fee.percent}%")
                result["details"]["buy_fee_percent"] = f"{buy_fee.percent}%"

                # Calculate actual fee amount
                trade_value = float(TEST_CONFIG["test_amount"]) * float(TEST_CONFIG["test_price"])
                fee_amount = trade_value * (float(buy_fee.percent) / 100)
                logger.info(f"   💸 Buy fee amount: {fee_amount:.6f} {TEST_CONFIG['quote_currency']}")
                result["details"]["buy_fee_amount"] = f"{fee_amount:.6f}"

            result["details"]["buy_fee"] = str(buy_fee)

            # Test sell order fee
            logger.info("🔍 Testing SELL order fee calculation...")
            sell_fee = self.connector.get_fee(
                base_currency=TEST_CONFIG["base_currency"],
                quote_currency=TEST_CONFIG["quote_currency"],
                order_type=OrderType.LIMIT,
                order_side=TradeType.SELL,
                amount=TEST_CONFIG["test_amount"],
                price=TEST_CONFIG["test_price"]
            )
            logger.info(f"   ✅ Sell order fee structure: {sell_fee}")

            # Extract fee details
            if hasattr(sell_fee, 'flat_fees'):
                logger.info(f"   📊 Sell flat fees: {sell_fee.flat_fees}")
                result["details"]["sell_flat_fees"] = str(sell_fee.flat_fees)
            if hasattr(sell_fee, 'percent'):
                logger.info(f"   📊 Sell fee percentage: {sell_fee.percent}%")
                result["details"]["sell_fee_percent"] = f"{sell_fee.percent}%"

                # Calculate actual fee amount
                trade_value = float(TEST_CONFIG["test_amount"]) * float(TEST_CONFIG["test_price"])
                fee_amount = trade_value * (float(sell_fee.percent) / 100)
                logger.info(f"   💸 Sell fee amount: {fee_amount:.6f} {TEST_CONFIG['quote_currency']}")
                result["details"]["sell_fee_amount"] = f"{fee_amount:.6f}"

            result["details"]["sell_fee"] = str(sell_fee)

            # Compare buy vs sell fees
            if hasattr(buy_fee, 'percent') and hasattr(sell_fee, 'percent'):
                buy_pct = float(buy_fee.percent)
                sell_pct = float(sell_fee.percent)
                if buy_pct == sell_pct:
                    logger.info(f"   ✅ Fee symmetry confirmed: {buy_pct}% for both sides")
                else:
                    logger.info(f"   📊 Fee asymmetry: Buy {buy_pct}% vs Sell {sell_pct}%")

            result["status"] = "PASSED"
            logger.info("✅ Fee calculation test PASSED")

        except Exception as e:
            logger.error(f"❌ Fee calculation test failed: {e}")
            logger.error(f"   🔍 Exception type: {type(e).__name__}")
            logger.error(f"   📝 Exception details: {str(e)}")
            result["status"] = "FAILED"
            result["errors"].append(str(e))

        return result

    async def test_order_placement(self) -> Dict[str, Any]:
        """Test real order placement"""
        logger.info("🛒 Testing real order placement...")

        result = {
            "test_name": "Order Placement",
            "status": "UNKNOWN",
            "details": {},
            "errors": []
        }

        try:
            # Place a safe buy order (way below market)
            logger.info("Placing test buy order...")
            order_id = f"test_buy_{TEST_CONFIG['base_currency'].lower()}_001"

            tx_hash, timestamp = await self.connector._create_order(
                trade_type=TradeType.BUY,
                order_id=order_id,
                trading_pair=TEST_CONFIG["trading_pair"],
                amount=TEST_CONFIG["test_amount"],
                order_type=OrderType.LIMIT,
                price=TEST_CONFIG["low_price"]  # Very low price to avoid fill
            )

            logger.info(f"✅ Order placed! TX Hash: {tx_hash}")
            result["details"]["buy_order_tx"] = tx_hash
            result["details"]["buy_order_timestamp"] = timestamp
            result["details"]["buy_order_id"] = order_id
            result["details"]["order_amount"] = str(TEST_CONFIG["test_amount"])
            result["details"]["order_price"] = str(TEST_CONFIG["low_price"])

            # Store order ID for cancellation test
            self.test_order_id = order_id

            result["status"] = "PASSED"
            logger.info("✅ Order placement test PASSED")

        except Exception as e:
            logger.error(f"❌ Order placement test failed: {e}")
            result["status"] = "FAILED"
            result["errors"].append(str(e))

        return result

    async def test_order_cancellation(self) -> Dict[str, Any]:
        """Test order cancellation"""
        logger.info("❌ Testing order cancellation...")

        result = {
            "test_name": "Order Cancellation",
            "status": "UNKNOWN",
            "details": {},
            "errors": []
        }

        try:
            if not hasattr(self, 'test_order_id'):
                result["status"] = "SKIPPED"
                result["errors"].append("No order to cancel (placement failed)")
                return result

            # Cancel the test order
            logger.info(f"Cancelling order: {self.test_order_id}")
            cancel_result = await self.connector._execute_cancel(
                order_id=self.test_order_id,
                cancel_age=30
            )

            logger.info(f"✅ Cancellation result: {cancel_result}")
            result["details"]["cancel_success"] = cancel_result.success
            result["details"]["cancel_order_id"] = cancel_result.order_id

            if cancel_result.success:
                result["status"] = "PASSED"
                logger.info("✅ Order cancellation test PASSED")
            else:
                result["status"] = "FAILED"
                result["errors"].append("Cancellation returned success=False")

        except Exception as e:
            logger.error(f"❌ Order cancellation test failed: {e}")
            result["status"] = "FAILED"
            result["errors"].append(str(e))

        return result

    async def test_balance_checking(self) -> Dict[str, Any]:
        """Test real balance checking"""
        print("💰 Testing balance checking...")
        print(f"   👛 Wallet: {TEST_CONFIG['wallet_address']}")
        print(f"   🎯 Base Token: {TEST_CONFIG['base_currency']} ({TEST_CONFIG['base_token_address']})")
        print(f"   🎯 Quote Token: {TEST_CONFIG['quote_currency']} ({TEST_CONFIG['quote_token_address']})")

        result = {
            "test_name": "Balance Checking",
            "status": "UNKNOWN",
            "details": {},
            "errors": []
        }

        try:
            # Update balances
            print("🔍 Updating balances from blockchain...")
            await self.connector._update_balances()

            # Check account balances
            balances = getattr(self.connector, '_account_balances', {})
            available = getattr(self.connector, '_account_available_balances', {})

            print(f"   📊 Raw account balances: {balances}")
            print(f"   📊 Raw available balances: {available}")

            result["details"]["account_balances"] = {k: str(v) for k, v in balances.items()}
            result["details"]["available_balances"] = {k: str(v) for k, v in available.items()}

            # Check if we have base currency balance
            base_token_address = TEST_CONFIG["base_token_address"]
            quote_token_address = TEST_CONFIG["quote_token_address"]

            base_balance = balances.get(base_token_address, Decimal("0"))
            quote_balance = balances.get(quote_token_address, Decimal("0"))

            print("")
            print("💰 BALANCE BREAKDOWN:")
            print(f"   🏛️  {TEST_CONFIG['base_currency']}: {base_balance}")
            print(f"   🏛️  {TEST_CONFIG['quote_currency']}: {quote_balance}")

            # Calculate USD value if we have prices
            try:
                if base_balance > 0:
                    mid_price = self.connector.get_mid_price(TEST_CONFIG["trading_pair"])
                    if mid_price and float(mid_price) > 0:
                        base_value = float(base_balance) * float(mid_price)
                        print(f"   💵 {TEST_CONFIG['base_currency']} Value: ~{base_value:.2f} {TEST_CONFIG['quote_currency']}")
                        result["details"]["base_value_quote"] = f"{base_value:.6f}"
            except Exception as e:
                print(f"   ⚠️  Could not calculate value: {e}")

            result["details"]["base_balance"] = str(base_balance)
            result["details"]["quote_balance"] = str(quote_balance)
            result["details"]["base_currency"] = TEST_CONFIG["base_currency"]
            result["details"]["quote_currency"] = TEST_CONFIG["quote_currency"]

            # Check for any other tokens
            other_tokens = {}
            for addr, bal in balances.items():
                if addr not in [base_token_address, quote_token_address] and bal > 0:
                    other_tokens[addr] = str(bal)
                    print(f"   🪙 Other Token ({addr[:6]}...{addr[-4:]}): {bal}")

            if other_tokens:
                result["details"]["other_tokens"] = other_tokens

            # Determine test result
            if base_balance > 0 or quote_balance > 0:
                result["status"] = "PASSED"
                print("✅ Balance checking test PASSED")
                print("   🎉 Found balances for trading!")

                # Check if we have enough for testing
                min_test_amount = TEST_CONFIG["test_amount"]
                if base_balance >= min_test_amount:
                    print(f"   ✅ Sufficient {TEST_CONFIG['base_currency']} for testing ({base_balance} >= {min_test_amount})")
                    result["details"]["can_trade_base"] = "true"
                else:
                    print(f"   ⚠️  Insufficient {TEST_CONFIG['base_currency']} for testing ({base_balance} < {min_test_amount})")
                    result["details"]["can_trade_base"] = "false"

            else:
                result["status"] = "FAILED"
                result["errors"].append(f"No {TEST_CONFIG['base_currency']} or {TEST_CONFIG['quote_currency']} balance found")
                print("   ❌ No tradeable balances found!")

        except Exception as e:
            print(f"❌ Balance checking test failed: {e}")
            print(f"   🔍 Exception type: {type(e).__name__}")
            print(f"   📝 Exception details: {str(e)}")
            result["status"] = "FAILED"
            result["errors"].append(str(e))

        return result

    async def run_all_tests(self):
        """Run all critical function tests"""
        logger.info("🚀 Starting Critical Functions Test Suite")
        logger.info("=" * 50)

        # Setup
        if not await self.setup_connector():
            logger.error("❌ Cannot continue - connector setup failed")
            return

        # Run tests in order
        tests = [
            self.test_balance_checking,
            self.test_fee_calculation,
            self.test_price_quotes,
            self.test_order_placement,
            self.test_order_cancellation
        ]

        for test_func in tests:
            try:
                print("-" * 50)
                print(f"🚀 STARTING: {test_func.__name__.replace('test_', '').replace('_', ' ').title()}")
                print("-" * 50)

                result = await test_func()
                self.test_results[result["test_name"]] = result

                # Display detailed results immediately after each test
                self._display_detailed_test_result(result)

            except Exception as e:
                print(f"❌ Test {test_func.__name__} crashed: {e}")
                print(f"   Exception details: {type(e).__name__}: {str(e)}")

        # Cleanup
        if self.connector:
            await self.connector.stop_network()

        # Print summary
        self.print_summary()

    def _display_detailed_test_result(self, result: Dict[str, Any]):
        """Display detailed results for each test"""
        test_name = result["test_name"]
        status = result["status"]
        details = result.get("details", {})
        errors = result.get("errors", [])

        print("")
        print("=" * 60)
        print(f"📊 DETAILED RESULTS: {test_name}")
        print("=" * 60)

        # Status with emoji
        if status == "PASSED":
            print(f"🎉 STATUS: ✅ {status}")
        elif status == "FAILED":
            print(f"💥 STATUS: ❌ {status}")
        else:
            print(f"⚠️  STATUS: {status}")

        # Display all details with formatting
        if details:
            print("")
            print("📋 DETAILED OUTPUT:")
            print("-" * 30)

            for key, value in details.items():
                # Format different types of data
                if key.endswith("_balance"):
                    currency = key.replace("_balance", "").upper()
                    print(f"   💰 {currency} Balance: {value}")
                elif key.endswith("_price"):
                    price_type = key.replace("_price", "").replace("_", " ").title()
                    print(f"   💵 {price_type} Price: {value}")
                elif key.endswith("_fee"):
                    fee_type = key.replace("_fee", "").replace("_", " ").title()
                    print(f"   💸 {fee_type} Fee: {value}")
                elif key.endswith("_tx") or key.endswith("_hash"):
                    print(f"   🔗 Transaction Hash: {value}")
                elif key.endswith("_timestamp"):
                    print(f"   ⏰ Timestamp: {value}")
                elif key.endswith("_id"):
                    print(f"   🏷️  Order ID: {value}")
                elif key.endswith("_amount"):
                    print(f"   📏 Amount: {value}")
                elif "balances" in key:
                    print(f"   📊 {key.replace('_', ' ').title()}:")
                    if isinstance(value, dict):
                        for addr, bal in value.items():
                            # Try to map token address to currency
                            currency = self._get_currency_from_address(addr)
                            print(f"     • {currency}: {bal}")
                    else:
                        print(f"     {value}")
                elif key in ["base_currency", "quote_currency"]:
                    print(f"   🏛️  {key.replace('_', ' ').title()}: {value}")
                elif key.endswith("_success"):
                    success_emoji = "✅" if str(value).lower() == "true" else "❌"
                    print(f"   {success_emoji} Success: {value}")
                else:
                    print(f"   📝 {key.replace('_', ' ').title()}: {value}")

        # Display errors with details
        if errors:
            print("")
            print("🚨 ERRORS ENCOUNTERED:")
            print("-" * 30)
            for i, error in enumerate(errors, 1):
                print(f"   {i}. ❌ {error}")

        # Add separator
        print("")
        print("🏁 " + "=" * 58 + " 🏁")
        print("")

    def _get_currency_from_address(self, address: str) -> str:
        """Map token address to currency symbol"""
        address_map = {
            TEST_CONFIG["base_token_address"]: TEST_CONFIG["base_currency"],
            TEST_CONFIG["quote_token_address"]: TEST_CONFIG["quote_currency"]
        }
        return address_map.get(address, f"Token({address[:6]}...{address[-4:]})")

    def print_summary(self):
        """Print comprehensive test results summary"""
        logger.info("\n" + "🎯" + "=" * 58 + "🎯")
        logger.info("📊 COMPREHENSIVE CRITICAL FUNCTIONS TEST SUMMARY")
        logger.info("🎯" + "=" * 58 + "🎯")

        # Test configuration summary
        logger.info("")
        logger.info("📋 TEST CONFIGURATION:")
        logger.info(f"   📈 Trading Pair: {TEST_CONFIG['trading_pair']}")
        logger.info(f"   🏛️  Base Currency: {TEST_CONFIG['base_currency']} ({TEST_CONFIG['base_token_address']})")
        logger.info(f"   🏛️  Quote Currency: {TEST_CONFIG['quote_currency']} ({TEST_CONFIG['quote_token_address']})")
        logger.info(f"   👛 Wallet: {TEST_CONFIG['wallet_address']}")
        logger.info(f"   🌐 Network: {TEST_CONFIG['chain'].title()} {TEST_CONFIG['network'].title()}")

        logger.info("")
        logger.info("📊 TEST RESULTS BREAKDOWN:")
        logger.info("-" * 40)

        passed = 0
        failed = 0
        skipped = 0

        # Detailed breakdown for each test
        for test_name, result in self.test_results.items():
            status = result["status"]
            details = result.get("details", {})
            errors = result.get("errors", [])

            if status == "PASSED":
                logger.info(f"✅ {test_name}: PASSED")
                passed += 1
                # Show key success metrics
                if test_name == "Balance Checking":
                    base_bal = details.get("base_balance", "0")
                    quote_bal = details.get("quote_balance", "0")
                    logger.info(f"   💰 {TEST_CONFIG['base_currency']}: {base_bal}")
                    logger.info(f"   💰 {TEST_CONFIG['quote_currency']}: {quote_bal}")
                elif test_name == "Order Placement":
                    tx_hash = details.get("buy_order_tx", "N/A")
                    amount = details.get("order_amount", "N/A")
                    price = details.get("order_price", "N/A")
                    logger.info(f"   🔗 TX: {tx_hash}")
                    logger.info(f"   📏 Amount: {amount} {TEST_CONFIG['base_currency']}")
                    logger.info(f"   💵 Price: {price} {TEST_CONFIG['quote_currency']}")
                elif test_name == "Fee Calculation":
                    buy_fee = details.get("buy_fee", "N/A")
                    sell_fee = details.get("sell_fee", "N/A")
                    logger.info(f"   💸 Buy Fee: {buy_fee}")
                    logger.info(f"   💸 Sell Fee: {sell_fee}")
                elif test_name == "Price Quotes":
                    buy_price = details.get("buy_price", "N/A")
                    sell_price = details.get("sell_price", "N/A")
                    mid_price = details.get("mid_price", "N/A")
                    logger.info(f"   💵 Buy: {buy_price}")
                    logger.info(f"   💵 Sell: {sell_price}")
                    logger.info(f"   💵 Mid: {mid_price}")

            elif status == "FAILED":
                logger.error(f"❌ {test_name}: FAILED")
                failed += 1
                for error in errors:
                    logger.error(f"   🚨 {error}")
            else:
                logger.warning(f"⚠️  {test_name}: {status}")
                skipped += 1
                for error in errors:
                    logger.warning(f"   ⚠️  {error}")

            logger.info("")

        # Final statistics
        logger.info("📈 FINAL STATISTICS:")
        logger.info("-" * 20)
        total_tests = passed + failed + skipped
        logger.info(f"   � Total Tests: {total_tests}")
        logger.info(f"   ✅ Passed: {passed}")
        logger.info(f"   ❌ Failed: {failed}")
        logger.info(f"   ⚠️  Skipped: {skipped}")

        if total_tests > 0:
            success_rate = (passed / total_tests) * 100
            logger.info(f"   📊 Success Rate: {success_rate:.1f}%")

        logger.info("")

        # Final verdict
        if failed == 0 and passed > 0:
            logger.info("🎉" + "=" * 50 + "🎉")
            logger.info("🚀 ALL CRITICAL TESTS PASSED! 🚀")
            logger.info("✅ Connector is READY for live trading!")
            logger.info("🎉" + "=" * 50 + "🎉")
        elif failed > 0:
            logger.warning("⚠️ " + "=" * 50 + " ⚠️")
            logger.warning(f"🔧 {failed} TESTS FAILED - REVIEW REQUIRED")
            logger.warning("⚠️  Fix issues before production use")
            logger.warning("⚠️ " + "=" * 50 + " ⚠️")
        else:
            logger.warning("❓ No tests completed successfully")

        logger.info("")


async def main():
    """Main test execution"""
    print("🔥 CRITICAL FUNCTIONS TEST")
    print("=========================")
    print("✅ Tests REAL trading functions")
    print("✅ Uses REAL tokens on testnet")
    print("✅ Single execution with cleanup")
    print()
    print("📊 CURRENT TEST CONFIGURATION:")
    print(f"   Trading Pair: {TEST_CONFIG['trading_pair']}")
    print(f"   Base Currency: {TEST_CONFIG['base_currency']} ({TEST_CONFIG['base_token_address']})")
    print(f"   Quote Currency: {TEST_CONFIG['quote_currency']} ({TEST_CONFIG['quote_token_address']})")
    print(f"   Wallet: {TEST_CONFIG['wallet_address']}")
    print(f"   Test Amount: {TEST_CONFIG['test_amount']}")
    print(f"   Test Price: {TEST_CONFIG['test_price']}")
    print(f"   Safe Order Price: {TEST_CONFIG['low_price']}")
    print()
    print("💡 To test different pairs, edit TEST_CONFIG at the top of this file")
    print()

    tester = CriticalFunctionsTest()
    await tester.run_all_tests()

if __name__ == "__main__":
    asyncio.run(main())
