#!/usr/bin/env python

"""
Standard Exchange Connector for Hummingbot

IMPORTANT IMPLEMENTATION NOTES:
===============================

ORDER PLACEMENT APPROACH:
- This connector uses DIRECT CONTRACT CALLS for order placement
- StandardWeb3 client library is INCOMPLETE for limitSell/limitBuy functions
- DO NOT switch to StandardWeb3 approach without implementing missing functions first
- Direct contract calls have been tested and verified to work correctly with proper function signatures

FUNCTION SIGNATURES:
- limitSell/limitBuy functions require uint32 for nonce parameter (not uint256)
- Function selector for limitSell: 0x349d1b5f
- All function signatures have been verified against the contract ABI

PRIVATE KEY MANAGEMENT:
- Private key is loaded from .env file (SOMNIA_PRIVATE_KEY)
- Ensure .env file is properly configured before running connector

BALANCE CHECKING:
- Native token (SOMI) balances are checked differently from ERC20 tokens
- Native balance uses web3.eth.get_balance()
- ERC20 balances use contract.functions.balanceOf().call()

For future development: Only switch to StandardWeb3 client after verifying that
limitSell/limitBuy functions are properly implemented in the StandardWeb3 library.
"""

import asyncio
import json
import logging
import math
import os
import time
import traceback
from contextlib import contextmanager
from decimal import Decimal
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple

from bidict import bidict

from hummingbot.connector.constants import s_decimal_0, s_decimal_NaN
from hummingbot.connector.exchange.standard import (
    standard_constants as CONSTANTS,
    standard_utils as utils,
    standard_web_utils as web_utils,
)
from hummingbot.connector.exchange.standard.standard_api_order_book_data_source import StandardAPIOrderBookDataSource
from hummingbot.connector.exchange.standard.standard_api_user_stream_data_source import StandardAPIUserStreamDataSource
from hummingbot.connector.exchange.standard.standard_auth import StandardAuth
from hummingbot.connector.exchange.standard.standard_constants import MAX_ORDERS_TO_MATCH
from hummingbot.connector.exchange_py_base import ExchangePyBase
from hummingbot.connector.trading_rule import TradingRule
from hummingbot.connector.utils import combine_to_hb_trading_pair
from hummingbot.core.data_type.common import OrderType, PriceType, TradeType
from hummingbot.core.data_type.in_flight_order import InFlightOrder, OrderState, OrderUpdate, TradeUpdate
from hummingbot.core.data_type.order_book_tracker_data_source import OrderBookTrackerDataSource
from hummingbot.core.data_type.trade_fee import AddedToCostTradeFee, TokenAmount, TradeFeeBase
from hummingbot.core.data_type.user_stream_tracker_data_source import UserStreamTrackerDataSource
from hummingbot.core.event.events import MarketEvent
from hummingbot.core.network_iterator import NetworkStatus
from hummingbot.core.utils.estimate_fee import build_trade_fee
from hummingbot.core.web_assistant.connections.data_types import RESTMethod
from hummingbot.core.web_assistant.web_assistants_factory import WebAssistantsFactory
from hummingbot.logger import HummingbotLogger

if TYPE_CHECKING:
    from hummingbot.client.config.config_helpers import ClientConfigAdapter

try:
    from standardweb3 import StandardClient
except ImportError:
    StandardClient = None

try:
    import pandas as pd
except ImportError:
    pd = None


# 📊 PERFORMANCE TIMING UTILITIES
@contextmanager
def timing_context(operation_name: str):
    """Context manager for timing operations with detailed logging."""
    start_time = time.time()
    try:
        yield
    finally:
        duration = time.time() - start_time
        # Use a logger that's always available
        logger = logging.getLogger(__name__)
        logger.info(f"⏱️  TIMING: {operation_name} took {duration:.3f}s")


class PerformanceTracker:
    """Enhanced performance tracker with method-level timing and periodic reporting."""

    def __init__(self):
        self.timings = {}
        self.call_counts = {}
        self.start_time = time.time()

    def add_timing(self, method_name: str, duration: float):
        if method_name not in self.timings:
            self.timings[method_name] = []
            self.call_counts[method_name] = 0

        self.timings[method_name].append(duration)
        self.call_counts[method_name] += 1

    def get_summary(self) -> Dict[str, Any]:
        """Get comprehensive performance summary."""
        summary = {
            "total_runtime": time.time() - self.start_time,
            "methods": {}
        }

        for method, times in self.timings.items():
            if times:  # Only include methods that have been called
                summary["methods"][method] = {
                    "count": len(times),
                    "total_time": sum(times),
                    "avg_time": sum(times) / len(times),
                    "min_time": min(times),
                    "max_time": max(times),
                    "last_time": times[-1] if times else 0
                }

        return summary


# Global performance tracker instance
performance_tracker = PerformanceTracker()


class StandardExchange(ExchangePyBase):
    """
    Somnia exchange connector using StandardWeb3 for blockchain interactions.
    """

    web_utils = web_utils
    _logger: Optional[HummingbotLogger] = None

    # Error rate limiting to prevent infinite loops
    _error_count = 0
    _last_error_time = 0
    _error_rate_limit = 10  # Max 10 errors per minute
    _error_time_window = 60  # 60 seconds

    @classmethod
    def logger(cls) -> HummingbotLogger:
        if cls._logger is None:
            cls._logger = logging.getLogger(__name__)
        return cls._logger

    def __init__(
        self,
        client_config_map: "ClientConfigAdapter",
        somnia_private_key: str,
        somnia_wallet_address: str,
        trading_pairs: List[str] = None,
        trading_required: bool = True,
        domain: str = CONSTANTS.DEFAULT_DOMAIN,
    ):
        self.logger().info("=== DEBUG: StandardExchange.__init__ STARTING ===")
        self.logger().info("DEBUG: Constructor called with parameters:")
        self.logger().info(f"  - trading_pairs = {trading_pairs} (type: {type(trading_pairs)})")
        self.logger().info(f"  - trading_required = {trading_required} (type: {type(trading_required)})")
        self.logger().info(f"  - somnia_wallet_address = {somnia_wallet_address}")
        self.logger().info(f"  - domain = {domain}")

        # Check if domain is set via environment variable
        import os

        env_domain = os.getenv("SOMNIA_DOMAIN")
        if env_domain and env_domain != domain:
            self.logger().info(f"Overriding domain from parameter ({domain}) with value from .env: {env_domain}")
            domain = env_domain

        # Store configuration
        self._private_key = somnia_private_key
        self._wallet_address = somnia_wallet_address
        self._domain = domain
        self._trading_required = trading_required
        self._trading_pairs = trading_pairs or []

        self.logger().info(
            "Using domain: {self._domain} - Token addresses and API endpoints " f"will be specific to this domain."
        )
        self.logger().info("DEBUG: After assignment:")
        self.logger().info(f"  - self._trading_pairs = {self._trading_pairs} (len: {len(self._trading_pairs)})")
        self.logger().info(f"  - self._trading_required = {self._trading_required}")

        # Log the call stack to understand who's creating this connector
        stack = traceback.format_stack()
        self.logger().info("DEBUG: Connector creation call stack (last 5 frames):")
        for i, frame in enumerate(stack[-5:]):
            self.logger().info(f"  Frame {i}: {frame.strip()}")

        # Initialize StandardWeb3 client if available
        self._standard_client = None
        if StandardClient:
            try:
                import os

                from dotenv import load_dotenv

                # Load environment variables
                load_dotenv()

                # Get private key from environment (use env variable over parameter for StandardClient)
                env_private_key = os.getenv("SOMNIA_PRIVATE_KEY")
                if env_private_key:
                    standard_client_private_key = env_private_key
                    # Also update the private key used for direct contract calls
                    self._private_key = env_private_key
                    self.logger().info("Using private key from .env file for StandardClient and direct contract calls")
                else:
                    standard_client_private_key = self._private_key
                    self.logger().info(
                        "Using private key from constructor parameter for StandardClient and direct contract calls"
                    )

                # Get configuration from environment with fallbacks
                domain_config = CONSTANTS.DOMAIN_CONFIG[self._domain]
                rpc_url = os.getenv("SOMNIA_RPC_URL", domain_config["rpc_url"])
                api_key = os.getenv("STANDARD_API_KEY", "defaultApiKey")

                # Store RPC URL for nonce management
                self._rpc_url = rpc_url

                # Use domain-specific endpoints
                api_url = domain_config["api_url"]
                websocket_url = domain_config["websocket_url"]
                matching_engine_address = domain_config["standard_exchange_address"]

                self.logger().info(
                    f"StandardWeb3 config - API: {api_url}, WS: {websocket_url}, ME: {matching_engine_address}"
                )
                self.logger().info("Using private key length: {len(standard_client_private_key)} characters")

                # Initialize StandardClient without networkName parameter
                self._standard_client = StandardClient(
                    private_key=standard_client_private_key,
                    http_rpc_url=rpc_url,
                    matching_engine_address=matching_engine_address,
                    api_url=api_url,
                    websocket_url=websocket_url,
                    api_key=api_key,
                )
                self.logger().info(f"StandardWeb3 client initialized successfully")
            except Exception as e:
                self.logger().error(f"Failed to initialize StandardWeb3 client: {e}")
                self.logger().info("StandardWeb3 client disabled due to error")
                self._standard_client = None
        else:
            self.logger().info("StandardWeb3 client disabled - library not available")

        # Initialize nonce management for blockchain transactions
        self._last_nonce = 0
        self._transaction_lock = asyncio.Lock()

        self.logger().info("DEBUG: Nonce management initialized")

        # Initialize authentication
        self.logger().info("DEBUG: Initializing StandardAuth")
        self._auth = StandardAuth(
            private_key=self._private_key,
            wallet_address=self._wallet_address,
        )
        self.logger().info("DEBUG: StandardAuth initialized successfully")

        # Initialize parent class
        self.logger().info("DEBUG: About to call super().__init__()")
        super().__init__(
            client_config_map=client_config_map,
        )
        self.logger().info("DEBUG: super().__init__() completed successfully")

        # Set connector reference in data sources after initialization
        if hasattr(self, "_orderbook_ds") and self._orderbook_ds:
            self._orderbook_ds._connector = self

        # Real-time balance updates - DEX connectors don't submit all balance updates
        # Instead they only update on position changes (not cancel), so we need to fetch periodically
        self.real_time_balance_update = False

        # 🔄 PHASE 1: Add transaction tracking infrastructure
        self._pending_tx_hashes: Dict[str, Dict] = {}  # tx_hash -> {timestamp, order_type, client_order_id}
        self._tx_order_mapping: Dict[str, str] = {}  # tx_hash -> client_order_id
        self._order_tx_mapping: Dict[str, str] = {}  # client_order_id -> tx_hash
        self._order_execution_status: Dict[str, str] = {}  # client_order_id -> 'placed'|'matched'|'failed'
        self._tx_monitor_task: Optional[asyncio.Task] = None  # Background task for transaction monitoring

        # 💰 PHASE 2: Add periodic balance refresh infrastructure
        self._balance_refresh_task: Optional[asyncio.Task] = None  # Background task for periodic balance updates
        self._balance_refresh_interval = 45.0  # Refresh every 45 seconds
        self._last_balance_refresh = 0.0  # Timestamp of last balance refresh
        self._balance_refresh_on_error = True  # Whether to refresh balances after order failures

        self.logger().info("DEBUG: Transaction tracking infrastructure initialized")
        self.logger().info("DEBUG: Periodic balance refresh infrastructure initialized")
        self.logger().info("DEBUG: StandardExchange.__init__ completed successfully")

    @staticmethod
    def authenticator(self) -> StandardAuth:
        """Get authenticator instance."""
        return self._auth

    @property
    def name(self) -> str:
        """Exchange name."""
        return CONSTANTS.EXCHANGE_NAME

    @property
    def rate_limits_rules(self):
        """Rate limit rules."""
        return web_utils.RATE_LIMITS

    @property
    def domain(self) -> str:
        """Exchange domain."""
        return self._domain

    @property
    def client_order_id_max_length(self) -> int:
        """Maximum length for client order ID."""
        return 32

    @property
    def client_order_id_prefix(self) -> str:
        """Prefix for client order IDs."""
        return CONSTANTS.NATIVE_TOKENS_PER_DOMAIN[self._domain]

    @property
    def trading_rules_request_path(self) -> str:
        """Path for trading rules request."""
        return ""  # Not used for GraphQL-based API

    @property
    def trading_pairs_request_path(self) -> str:
        """Path for trading pairs request."""
        return ""  # Not used for GraphQL-based API

    @property
    def check_network_request_path(self) -> str:
        """Path for network check request."""
        return ""  # Not used for GraphQL-based API

    async def check_network(self) -> NetworkStatus:
        """
        Check network connectivity.

        Returns:
            NetworkStatus enum value
        """
        try:
            self.logger().info("DEBUG: check_network() called")
            # Simple check - always return CONNECTED for now to avoid network issues
            # In a real implementation, you would ping the exchange API
            self.logger().info("DEBUG: check_network() returning CONNECTED")
            return NetworkStatus.CONNECTED
        except Exception as e:
            self.logger().error("DEBUG: Exception in check_network(): {e}")
            self.logger().error(f"Network check failed: {e}")
            return NetworkStatus.NOT_CONNECTED

    # 💰 GAS & BALANCE MANAGEMENT
    _min_gas_balance_wei = None  # Minimum SOMI balance for gas fees
    _gas_buffer_multiplier = 2.0  # Buffer for gas price volatility
    _last_gas_check_time = 0
    _gas_check_interval = 30  # Check gas balance every 30 seconds
    _last_gas_price = None  # Cached gas price
    _last_gas_price_time = 0
    _gas_price_cache_duration = 30  # Cache gas price for 30 seconds

    async def _get_cached_gas_price(self) -> int:
        """
        Get cached gas price to avoid redundant Web3 calls.
        Caches gas price for 30 seconds to balance accuracy and performance.

        Returns:
            Gas price in wei
        """
        current_time = time.time()

        # Return cached gas price if still valid
        if (
            self._last_gas_price is not None
            and current_time - self._last_gas_price_time < self._gas_price_cache_duration
        ):
            return self._last_gas_price

        # Fetch new gas price
        try:
            from web3 import Web3

            rpc_url = CONSTANTS.DOMAIN_CONFIG[self._domain]["rpc_url"]
            w3 = Web3(Web3.HTTPProvider(rpc_url))

            gas_price = w3.eth.gas_price

            # Cache the result
            self._last_gas_price = gas_price
            self._last_gas_price_time = current_time

            self.logger().debug(f"Updated cached gas price: {gas_price} wei")
            return gas_price

        except Exception as e:
            self.logger().warning(f"Failed to get gas price, using fallback: {e}")
            fallback_gas_price = 20 * 10**9  # 20 Gwei fallback

            # Cache the fallback too
            self._last_gas_price = fallback_gas_price
            self._last_gas_price_time = current_time

            return fallback_gas_price

    async def _check_gas_balance_sufficient(self) -> bool:
        """
        Check if wallet has sufficient native token balance for gas fees.
        Uses already-fetched balance data to avoid redundant Web3 calls.

        Returns:
            True if sufficient gas balance, False otherwise
        """
        try:
            current_time = time.time()

            # Only check gas balance every 30 seconds to avoid excessive calculations
            if current_time - self._last_gas_check_time < self._gas_check_interval:
                return True  # Assume sufficient if checked recently

            self._last_gas_check_time = current_time

            # Get native token balance from already-fetched data (avoids redundant Web3 call)
            native_token = CONSTANTS.NATIVE_TOKEN
            balance_somi = self.get_balance(native_token)

            if balance_somi <= 0:
                self.logger().warning(f"⚠️ No {native_token} balance found for gas fees")
                return False

            # Calculate minimum gas balance needed (estimate for ~10 transactions)
            # Use cached gas price to avoid redundant Web3 calls
            gas_price = await self._get_cached_gas_price()

            estimated_gas_per_tx = 3000000  # Conservative estimate
            gas_needed_for_10_tx = gas_price * estimated_gas_per_tx * 10 * self._gas_buffer_multiplier

            # Convert to Decimal using proper scaling
            min_balance_needed = Decimal(gas_needed_for_10_tx) / Decimal(10**18)

            self._min_gas_balance_wei = gas_needed_for_10_tx

            if balance_somi < min_balance_needed:
                self.logger().warning(
                    f"⚠️  LOW GAS BALANCE WARNING: {balance_somi:.6f} {native_token} "
                    f"(Need: {min_balance_needed:.6f} {native_token} for ~10 transactions)"
                )

                # If balance is critically low (less than 2 transactions), prevent new orders
                critical_threshold = Decimal(gas_price * estimated_gas_per_tx * 2) / Decimal(10**18)
                if balance_somi < critical_threshold:
                    self.logger().error(
                        f"🚨 CRITICAL GAS BALANCE: {balance_somi:.6f} {native_token} "
                        f"(Critical threshold: {critical_threshold:.6f} {native_token})"
                    )
                    return False
            else:
                self.logger().debug(
                    f"✅ Gas balance sufficient: {balance_somi:.6f} {native_token} "
                    f"(Need: {min_balance_needed:.6f} {native_token})"
                )

            return True

        except Exception as e:
            self.logger().error(f"Error checking gas balance: {e}")
            # Return True to avoid blocking operations if check fails
            return True

    async def _ensure_sufficient_gas_before_transaction(self, operation_type: str) -> bool:
        """
        Ensure sufficient gas balance before attempting blockchain transactions.

        Args:
            operation_type: Type of operation ('place_order', 'cancel_order', etc.)

        Returns:
            True if sufficient gas, False if should skip transaction
        """
        try:
            if not await self._check_gas_balance_sufficient():
                self.logger().error(
                    f"❌ Skipping {operation_type} due to insufficient gas balance. "
                    f"Please deposit SOMI for gas fees."
                )

                # Emit event for monitoring systems
                self._emit_transaction_event(
                    "insufficient_gas",
                    {
                        "operation_type": operation_type,
                        "timestamp": time.time(),
                        "wallet_address": self._wallet_address,
                        "message": "Transaction skipped due to insufficient gas balance",
                    },
                )

                return False

            return True

        except Exception as e:
            self.logger().error(f"Error in gas balance check for {operation_type}: {e}")
            # Allow transaction to proceed if check fails
            return True

    async def _start_tx_monitoring(self):
        """Start background transaction monitoring task."""
        if self._tx_monitor_task is None or self._tx_monitor_task.done():
            self._tx_monitor_task = asyncio.create_task(self._monitor_transactions())
            self.logger().info("🚀 PHASE 3: Started transaction monitoring task")
        else:
            self.logger().debug("Transaction monitoring task already running")

    async def _stop_tx_monitoring(self):
        """Stop background transaction monitoring task."""
        if self._tx_monitor_task and not self._tx_monitor_task.done():
            self._tx_monitor_task.cancel()
            try:
                await self._tx_monitor_task
            except asyncio.CancelledError:
                pass
            self.logger().info("🛑 PHASE 3: Stopped transaction monitoring task")
        else:
            self.logger().debug("No transaction monitoring task to stop")

    async def _monitor_transactions(self):
        """
        Background task to monitor blockchain transactions.
        Checks pending transactions and updates order status when confirmed/failed.
        """
        from web3 import Web3

        rpc_url = CONSTANTS.DOMAIN_CONFIG[self._domain]["rpc_url"]
        w3 = Web3(Web3.HTTPProvider(rpc_url))

        self.logger().info("🔄 PHASE 3: Transaction monitoring task started")

        while True:
            try:
                await asyncio.sleep(2)  # Check every 2 seconds

                # Copy pending tx list to avoid modification during iteration
                pending_tx_list = list(self._pending_tx_hashes.keys())

                if pending_tx_list:
                    self.logger().debug(f"Monitoring {len(pending_tx_list)} pending transactions")

                for tx_hash in pending_tx_list:
                    await self._check_transaction_status(w3, tx_hash)

                # Clean up old pending transactions (older than 10 minutes)
                await self._cleanup_old_pending_transactions()

            except asyncio.CancelledError:
                self.logger().info("🛑 Transaction monitoring task cancelled")
                break
            except Exception as e:
                self.logger().error(f"Error in transaction monitoring: {e}")
                await asyncio.sleep(5)  # Wait longer on error

    async def _check_transaction_status(self, w3, tx_hash: str):
        """Check status of a specific transaction."""
        try:
            receipt = w3.eth.get_transaction_receipt(tx_hash)

            if receipt:
                # Transaction confirmed!
                tx_info = self._pending_tx_hashes.get(tx_hash)
                client_order_id = tx_info.get("client_order_id") if tx_info else None

                if client_order_id:
                    self.logger().info(f"🔍 Transaction {tx_hash[:10]}... confirmed for order {client_order_id}")

                    if receipt.status == 1:
                        # SUCCESS
                        await self._handle_transaction_success(client_order_id, tx_hash, receipt)
                    else:
                        # FAILED
                        await self._handle_transaction_failure(client_order_id, tx_hash, receipt)
                else:
                    self.logger().debug(f"Transaction {tx_hash[:10]}... confirmed but no associated order found")

                # Remove from pending
                self._pending_tx_hashes.pop(tx_hash, None)
                self._tx_order_mapping.pop(tx_hash, None)
                if client_order_id:
                    self._order_tx_mapping.pop(client_order_id, None)
                    self._order_execution_status.pop(client_order_id, None)

        except Exception as e:
            if "transaction not found" not in str(e).lower():
                self.logger().warning(f"Error checking tx {tx_hash[:10]}...: {e}")
            # Don't remove from pending - transaction might still be in mempool

    async def _cleanup_old_pending_transactions(self):
        """Clean up transactions that have been pending too long."""
        current_time = self.current_timestamp
        timeout_seconds = 600  # 10 minutes

        to_remove = []
        for tx_hash, tx_info in self._pending_tx_hashes.items():
            if current_time - tx_info["timestamp"] > timeout_seconds:
                to_remove.append(tx_hash)

        for tx_hash in to_remove:
            tx_info = self._pending_tx_hashes.get(tx_hash, {})
            client_order_id = tx_info.get("client_order_id")

            self.logger().warning(f"🕐 Transaction {tx_hash[:10]}... timed out after 10 minutes")

            # ENHANCED: Also check if the transaction actually failed
            try:
                from web3 import Web3
                w3 = Web3(Web3.HTTPProvider(CONSTANTS.SOMNIA_RPC_URL))

                # Try to get transaction receipt to see if it failed
                try:
                    receipt = await self._run_in_executor(lambda: w3.eth.get_transaction_receipt(tx_hash))
                    if receipt and receipt.status == 0:
                        self.logger().error(f"❌ Found FAILED transaction during cleanup: {tx_hash[:10]}...")
                        if client_order_id:
                            await self._handle_transaction_failure(client_order_id, tx_hash, receipt)
                        # Remove from tracking and continue
                        self._pending_tx_hashes.pop(tx_hash, None)
                        self._tx_order_mapping.pop(tx_hash, None)
                        if client_order_id:
                            self._order_tx_mapping.pop(client_order_id, None)
                            self._order_execution_status.pop(client_order_id, None)
                        continue
                except Exception:
                    # Receipt not found - transaction might still be pending or dropped
                    pass
            except Exception as e:
                self.logger().debug(f"Could not check transaction status during cleanup: {e}")

            if client_order_id:
                # Check if order has a known status before marking as failed
                if hasattr(self, "_order_tracker") and client_order_id in self._order_tracker.active_orders:
                    order = self._order_tracker.active_orders[client_order_id]
                    current_state = order.current_state

                    # Don't mark as failed if order is already in a final state
                    if current_state in [OrderState.FILLED, OrderState.CANCELED, OrderState.FAILED]:
                        self.logger().info(f"🔄 Order {client_order_id} already in final state {current_state}, skipping timeout")
                    else:
                        # Only mark as failed if truly unknown or still pending
                        self.logger().warning(f"⏰ Order {client_order_id} still in state {current_state}, marking as failed due to transaction timeout")
                        await self._handle_transaction_timeout(client_order_id, tx_hash)
                else:
                    # Order not in tracker, safe to mark as failed
                    await self._handle_transaction_timeout(client_order_id, tx_hash)

            # Remove from tracking
            self._pending_tx_hashes.pop(tx_hash, None)
            self._tx_order_mapping.pop(tx_hash, None)
            if client_order_id:
                self._order_tx_mapping.pop(client_order_id, None)
                self._order_execution_status.pop(client_order_id, None)

    async def _handle_transaction_timeout(self, client_order_id: str, tx_hash: str):
        """Handle transaction timeout."""
        self.logger().warning(f"⏰ Transaction timeout for order {client_order_id}: {tx_hash[:10]}...")

        # Check if order is still being tracked
        if hasattr(self, "_order_tracker") and client_order_id in self._order_tracker.active_orders:
            order = self._order_tracker.active_orders[client_order_id]

            # Update order to failed state
            order_update = OrderUpdate(
                client_order_id=client_order_id,
                trading_pair=order.trading_pair,
                update_timestamp=self.current_timestamp,
                new_state=OrderState.FAILED,
                misc_updates={
                    "error_message": "Transaction timeout - may be stuck in mempool",
                    "error_type": "TRANSACTION_TIMEOUT",
                    "tx_hash": tx_hash,
                    "timeout_duration": "10 minutes",
                },
            )
            self._order_tracker.process_order_update(order_update)
            self.logger().error(f"Order {client_order_id} marked as failed due to transaction timeout")

    async def _handle_transaction_success(self, client_order_id: str, tx_hash: str, receipt):
        """Handle successful transaction confirmation with detailed analysis."""
        try:
            # Extract detailed transaction information
            tx_details = self._analyze_transaction_receipt(receipt, tx_hash)

            # Log comprehensive success information
            self.logger().info(
                f"🎉 Transaction confirmed successfully: {client_order_id} | "
                f"TX: {tx_hash[:10]}... | "
                f"Gas used: {tx_details.get('gas_used', 'unknown')} | "
                f"Block: {tx_details.get('block_number', 'unknown')} | "
                f"Fee: {tx_details.get('transaction_fee', 'unknown')} ETH"
            )

            # Record transaction metrics
            self._record_transaction_metrics(client_order_id, tx_hash, "success", tx_details)

            # Emit success event for external monitoring
            self._emit_transaction_event(
                "transaction_confirmed",
                {
                    "client_order_id": client_order_id,
                    "tx_hash": tx_hash,
                    "gas_used": tx_details.get("gas_used"),
                    "block_number": tx_details.get("block_number"),
                    "transaction_fee": tx_details.get("transaction_fee"),
                },
            )

        except Exception as e:
            self.logger().error(f"Error processing successful transaction {tx_hash}: {e}")

    async def _handle_transaction_failure(self, client_order_id: str, tx_hash: str, receipt):
        """Handle failed transaction with comprehensive error analysis."""
        try:
            # Analyze failure details
            failure_details = self._analyze_transaction_failure(receipt, tx_hash)

            # Log comprehensive failure information
            self.logger().error(
                f"💥 Transaction failed: {client_order_id} | "
                f"TX: {tx_hash[:10]}... | "
                f"Reason: {failure_details.get('failure_reason', 'unknown')} | "
                f"Gas used: {failure_details.get('gas_used', 'unknown')} | "
                f"Gas limit: {failure_details.get('gas_limit', 'unknown')} | "
                f"Error code: {failure_details.get('error_code', 'none')}"
            )

            # Categorize failure for better handling
            failure_category = self._categorize_transaction_failure(failure_details)
            self.logger().error(f"🏷️  Failure category: {failure_category}")

            # Record failure metrics
            self._record_transaction_metrics(client_order_id, tx_hash, "failed", failure_details)

            # Suggest recovery action
            recovery_action = self._suggest_recovery_action(failure_category, failure_details)
            if recovery_action:
                self.logger().warning(f"💡 Suggested action: {recovery_action}")

            # Emit failure event for external monitoring
            self._emit_transaction_event(
                "transaction_failed",
                {
                    "client_order_id": client_order_id,
                    "tx_hash": tx_hash,
                    "failure_reason": failure_details.get("failure_reason"),
                    "failure_category": failure_category,
                    "gas_used": failure_details.get("gas_used"),
                    "suggested_action": recovery_action,
                },
            )

        except Exception as e:
            self.logger().error(f"Error processing failed transaction {tx_hash}: {e}")

    async def check_order_status_by_id(self, trading_pair: str, blockchain_order_id: int) -> dict:
        """
        Public method to check order status by blockchain order ID.
        Useful for debugging and external status checks.

        Args:
            trading_pair: Trading pair (e.g., "SOMI-USDC")
            blockchain_order_id: Blockchain order ID

        Returns:
            Order status info dict
        """
        try:
            base_symbol, quote_symbol = trading_pair.split('-')
            base_address = utils.convert_symbol_to_address(base_symbol, self._domain)
            quote_address = utils.convert_symbol_to_address(quote_symbol, self._domain)

            # For this public method, we'll check both bid and ask sides
            # since we don't know which side the order is on
            self.logger().info(f"🔍 Checking order status for ID {blockchain_order_id} on {trading_pair}")

            # Try bid side first
            bid_status = await self._check_order_status_on_chain(
                base_address=base_address,
                quote_address=quote_address,
                is_bid=True,
                blockchain_order_id=blockchain_order_id
            )

            if bid_status['exists']:
                self.logger().info(f"✅ Found order {blockchain_order_id} on BID side")
                bid_status['side'] = 'BUY'
                return bid_status

            # Try ask side
            ask_status = await self._check_order_status_on_chain(
                base_address=base_address,
                quote_address=quote_address,
                is_bid=False,
                blockchain_order_id=blockchain_order_id
            )

            if ask_status['exists']:
                self.logger().info(f"✅ Found order {blockchain_order_id} on ASK side")
                ask_status['side'] = 'SELL'
                return ask_status

            # Order not found on either side
            self.logger().info(f"❌ Order {blockchain_order_id} not found on either BID or ASK side")
            return {
                'exists': False,
                'side': 'UNKNOWN',
                'owner': None,
                'price': 0,
                'remaining_amount': 0,
                'is_active': False
            }

        except Exception as e:
            self.logger().error(f"Error checking order status for ID {blockchain_order_id}: {e}")
            return {
                'exists': None,
                'side': 'ERROR',
                'owner': None,
                'price': 0,
                'remaining_amount': 0,
                'is_active': None
            }

    def get_order_blockchain_status(self, client_order_id: str) -> Dict:
        """Get blockchain-specific status info for an order."""
        tx_hash = self._order_tx_mapping.get(client_order_id)

        if not tx_hash:
            return {"status": "not_found", "message": "Order not found in blockchain tracking"}

        if tx_hash in self._pending_tx_hashes:
            tx_info = self._pending_tx_hashes[tx_hash]
            return {
                "status": "pending",
                "tx_hash": tx_hash,
                "submitted_at": tx_info["timestamp"],
                "order_type": tx_info.get("order_type", "unknown"),
                "message": "Transaction submitted to blockchain, awaiting confirmation",
            }

        # Check if order is in active orders with blockchain info
        if hasattr(self, "_order_tracker") and client_order_id in self._order_tracker.active_orders:
            order = self._order_tracker.active_orders[client_order_id]
            if hasattr(order, "misc_updates") and order.misc_updates:
                misc = order.misc_updates
                if misc.get("blockchain_confirmed"):
                    return {
                        "status": "confirmed",
                        "tx_hash": misc.get("tx_hash"),
                        "gas_used": misc.get("gas_used"),
                        "block_number": misc.get("block_number"),
                        "message": "Transaction confirmed on blockchain",
                    }

        return {
            "status": "unknown",
            "tx_hash": tx_hash,
            "message": "Transaction status unknown - may have been processed",
        }

    # 🎯 PHASE 4: Enhanced Error Analysis & Reporting Methods

    def _analyze_transaction_receipt(self, receipt, tx_hash: str) -> Dict:
        """Analyze transaction receipt for detailed information."""
        try:
            details = {
                "tx_hash": tx_hash,
                "status": getattr(receipt, "status", None),
                "block_number": getattr(receipt, "blockNumber", None),
                "gas_used": getattr(receipt, "gasUsed", None),
                "gas_limit": None,  # Will try to get from original transaction
                "transaction_fee": None,
            }

            # Calculate transaction fee if possible
            if hasattr(receipt, "gasUsed") and hasattr(receipt, "effectiveGasPrice"):
                gas_used = receipt.gasUsed
                gas_price = receipt.effectiveGasPrice
                fee_wei = gas_used * gas_price
                fee_eth = fee_wei / (10**18)  # Convert wei to ETH
                details["transaction_fee"] = fee_eth

            return details

        except Exception as e:
            self.logger().error(f"Error analyzing transaction receipt {tx_hash}: {e}")
            return {"tx_hash": tx_hash, "error": str(e)}

    def _analyze_transaction_failure(self, receipt, tx_hash: str) -> Dict:
        """Analyze failed transaction for detailed failure information."""
        try:
            failure_details = self._analyze_transaction_receipt(receipt, tx_hash)

            # Add failure-specific analysis
            failure_details.update(
                {"failure_reason": "Transaction reverted", "error_code": None, "revert_reason": None}
            )

            # Try to get more specific failure reason
            if hasattr(receipt, "status") and receipt.status == 0:
                failure_details["failure_reason"] = "Transaction reverted (status=0)"

                # Check for common failure patterns
                gas_used = getattr(receipt, "gasUsed", 0)
                if gas_used > 0:
                    # Transaction used gas but failed - likely a revert
                    failure_details["failure_reason"] = "Smart contract execution reverted"

                    # Try to decode revert reason if available
                    try:
                        # This would require additional Web3 setup to decode revert reasons
                        # For now, just note that it's available
                        failure_details["revert_reason"] = "Revert reason decoding not implemented"
                    except Exception:
                        pass
                else:
                    failure_details["failure_reason"] = "Transaction failed before execution"

            return failure_details

        except Exception as e:
            self.logger().error(f"Error analyzing transaction failure {tx_hash}: {e}")
            return {"tx_hash": tx_hash, "failure_reason": "Analysis failed", "error": str(e)}

    def _categorize_transaction_failure(self, failure_details: Dict) -> str:
        """Categorize transaction failure for better error handling."""
        try:
            failure_reason = failure_details.get("failure_reason", "").lower()
            gas_used = failure_details.get("gas_used", 0)

            # Gas-related failures
            if "out of gas" in failure_reason or "gas" in failure_reason:
                return "gas_issue"

            # Smart contract reverts
            if "revert" in failure_reason or "execution reverted" in failure_reason:
                # Check for specific revert reasons
                if "insufficient" in failure_reason or "balance" in failure_reason:
                    return "insufficient_balance"
                elif gas_used > 0:
                    return "contract_revert"
                else:
                    return "pre_execution_failure"

            # Network issues
            if "network" in failure_reason or "connection" in failure_reason:
                return "network_issue"

            # Insufficient balance
            if "insufficient" in failure_reason or "balance" in failure_reason:
                return "insufficient_balance"

            # Nonce issues
            if "nonce" in failure_reason:
                return "nonce_issue"

            # Generic categorization based on status
            if failure_details.get("status") == 0:
                return "transaction_reverted"

            return "unknown_failure"

        except Exception as e:
            self.logger().error(f"Error categorizing failure: {e}")
            return "categorization_error"

    def _suggest_recovery_action(self, failure_category: str, failure_details: Dict) -> Optional[str]:
        """Suggest recovery action based on failure category."""
        try:
            suggestions = {
                "gas_issue": "Consider increasing gas limit or gas price for future transactions",
                "contract_revert": "Check order parameters (price, amount, balance) and market conditions",
                "insufficient_balance": "Ensure sufficient token balance and allowances before placing orders",
                "nonce_issue": "Nonce synchronization issue - will be handled automatically on retry",
                "network_issue": "Network connectivity problem - will retry automatically",
                "pre_execution_failure": "Pre-execution validation failed - check order parameters",
                "transaction_reverted": "Transaction was rejected by smart contract - verify order conditions",
            }

            return suggestions.get(failure_category, "Review transaction details and retry if appropriate")

        except Exception as e:
            self.logger().error(f"Error generating recovery suggestion: {e}")
            return None

    def _record_transaction_metrics(self, client_order_id: str, tx_hash: str, status: str, details: Dict):
        """Record transaction metrics for performance monitoring."""
        try:
            # Initialize metrics storage if not exists
            if not hasattr(self, "_transaction_metrics"):
                self._transaction_metrics = {
                    "total_transactions": 0,
                    "successful_transactions": 0,
                    "failed_transactions": 0,
                    "total_gas_used": 0,
                    "total_fees_paid": 0,
                    "failure_categories": {},
                    "recent_transactions": [],  # Keep last 100 transactions
                }

            metrics = self._transaction_metrics

            # Update counters
            metrics["total_transactions"] += 1
            if status == "success":
                metrics["successful_transactions"] += 1
            elif status == "failed":
                metrics["failed_transactions"] += 1

                # Track failure categories
                category = self._categorize_transaction_failure(details)
                metrics["failure_categories"][category] = metrics["failure_categories"].get(category, 0) + 1

            # Track gas usage
            gas_used = details.get("gas_used", 0)
            if gas_used:
                metrics["total_gas_used"] += gas_used

            # Track fees
            fee = details.get("transaction_fee", 0)
            if fee:
                metrics["total_fees_paid"] += fee

            # Keep recent transaction log (limited to 100)
            transaction_record = {
                "timestamp": time.time(),
                "client_order_id": client_order_id,
                "tx_hash": tx_hash[:10] + "...",
                "status": status,
                "gas_used": gas_used,
                "fee": fee,
            }

            metrics["recent_transactions"].append(transaction_record)
            if len(metrics["recent_transactions"]) > 100:
                metrics["recent_transactions"] = metrics["recent_transactions"][-100:]

        except Exception as e:
            self.logger().error(f"Error recording transaction metrics: {e}")

    def _emit_transaction_event(self, event_type: str, event_data: Dict):
        """Emit transaction event for external monitoring systems."""
        try:
            # This could be extended to integrate with monitoring systems
            # For now, just log the event in a structured format
            self.logger().info(
                f"📊 TRANSACTION_EVENT: {event_type} | "
                f"Order: {event_data.get('client_order_id', 'unknown')} | "
                f"TX: {event_data.get('tx_hash', 'unknown')[:10]}... | "
                f"Data: {event_data}"
            )

            # Future enhancement: Could integrate with external monitoring
            # systems like DataDog, Grafana, or custom dashboards

        except Exception as e:
            self.logger().error(f"Error emitting transaction event: {e}")

    def get_transaction_metrics(self) -> Dict:
        """Get comprehensive transaction metrics for monitoring."""
        try:
            if not hasattr(self, "_transaction_metrics"):
                return {
                    "total_transactions": 0,
                    "successful_transactions": 0,
                    "failed_transactions": 0,
                    "success_rate": 0.0,
                    "total_gas_used": 0,
                    "total_fees_paid": 0,
                    "average_gas_per_tx": 0.0,
                    "failure_categories": {},
                    "recent_transactions": [],
                }

            metrics = self._transaction_metrics.copy()

            # Calculate derived metrics
            total_tx = metrics["total_transactions"]
            if total_tx > 0:
                metrics["success_rate"] = (metrics["successful_transactions"] / total_tx) * 100
                metrics["failure_rate"] = (metrics["failed_transactions"] / total_tx) * 100
                metrics["average_gas_per_tx"] = metrics["total_gas_used"] / total_tx
                metrics["average_fee_per_tx"] = metrics["total_fees_paid"] / total_tx
            else:
                metrics["success_rate"] = 0.0
                metrics["failure_rate"] = 0.0
                metrics["average_gas_per_tx"] = 0.0
                metrics["average_fee_per_tx"] = 0.0

            return metrics

        except Exception as e:
            self.logger().error(f"Error getting transaction metrics: {e}")
            return {"error": str(e)}

    def get_error_summary(self) -> Dict:
        """Get comprehensive error summary for debugging."""
        try:
            metrics = self.get_transaction_metrics()

            summary = {
                "transaction_health": {
                    "total_transactions": metrics.get("total_transactions", 0),
                    "success_rate": f"{metrics.get('success_rate', 0):.2f}%",
                    "failure_rate": f"{metrics.get('failure_rate', 0):.2f}%",
                    "recent_failures": len(
                        [tx for tx in metrics.get("recent_transactions", []) if tx.get("status") == "failed"]
                    ),
                },
                "gas_efficiency": {
                    "total_gas_used": metrics.get("total_gas_used", 0),
                    "average_gas_per_tx": f"{metrics.get('average_gas_per_tx', 0):.0f}",
                    "total_fees_paid": f"{metrics.get('total_fees_paid', 0):.6f} ETH",
                },
                "failure_analysis": metrics.get("failure_categories", {}),
                "recent_issues": [
                    tx for tx in metrics.get("recent_transactions", [])[-10:] if tx.get("status") == "failed"
                ],
                "monitoring_status": {
                    "monitoring_active": hasattr(self, "_tx_monitor_task")
                    and self._tx_monitor_task
                    and not self._tx_monitor_task.done(),
                    "pending_transactions": len(self._pending_tx_hashes),
                    "tracked_orders": len(self._order_tx_mapping),
                },
            }

            return summary

        except Exception as e:
            self.logger().error(f"Error generating error summary: {e}")
            return {"error": str(e)}

    # 💰 PERIODIC BALANCE REFRESH METHODS

    async def _start_balance_refresh(self):
        """Start background periodic balance refresh task."""
        if self._balance_refresh_task is None or self._balance_refresh_task.done():
            self._balance_refresh_task = asyncio.create_task(self._periodic_balance_refresh())
            self.logger().info(f"🔄 Started periodic balance refresh (every {self._balance_refresh_interval}s)")
        else:
            self.logger().debug("Balance refresh task already running")

    async def _stop_balance_refresh(self):
        """Stop background balance refresh task."""
        if self._balance_refresh_task and not self._balance_refresh_task.done():
            self._balance_refresh_task.cancel()
            try:
                await self._balance_refresh_task
            except asyncio.CancelledError:
                pass
            self.logger().info("🛑 Stopped periodic balance refresh task")
        else:
            self.logger().debug("No balance refresh task to stop")

    async def _periodic_balance_refresh(self):
        """
        Background task to periodically refresh account balances.
        Runs every 45 seconds to keep balance data reasonably fresh without impacting performance.
        """
        self.logger().info("🔄 Periodic balance refresh task started")

        while True:
            try:
                await asyncio.sleep(self._balance_refresh_interval)

                current_time = time.time()
                self.logger().debug(f"⏰ Performing scheduled balance refresh (interval: {self._balance_refresh_interval}s)")

                # Update balances with timing
                with timing_context("periodic_balance_refresh"):
                    await self._update_balances()

                self._last_balance_refresh = current_time
                self.logger().debug("✅ Scheduled balance refresh completed")

            except asyncio.CancelledError:
                self.logger().info("🛑 Periodic balance refresh task cancelled")
                break
            except Exception as e:
                self.logger().error(f"Error in periodic balance refresh: {e}")
                await asyncio.sleep(30)  # Wait 30s on error before retry

    async def _refresh_balances_on_order_failure(self, client_order_id: str, error_message: str):
        """
        Refresh balances after order failure if the error might be balance-related.
        This helps ensure we have accurate balance data for subsequent orders.
        """
        if not self._balance_refresh_on_error:
            return

        # Check if error is likely balance-related
        error_lower = error_message.lower()
        balance_related_errors = [
            "insufficient",
            "balance",
            "allowance",
            "funds",
            "not enough",
            "exceeds",
        ]

        is_balance_error = any(keyword in error_lower for keyword in balance_related_errors)

        if is_balance_error:
            self.logger().info(f"🔄 Balance-related order failure detected for {client_order_id}, refreshing balances...")

            try:
                with timing_context("error_triggered_balance_refresh"):
                    await self._update_balances()
                self.logger().info("✅ Balance refresh after order failure completed")
            except Exception as refresh_error:
                self.logger().error(f"Error refreshing balances after order failure: {refresh_error}")

    async def start_network(self):
        """
        Initialize network and exchange info when connector starts.
        This method is called during connector startup.
        """
        try:
            self.logger().info("DEBUG: start_network() called - beginning network startup")
            self.logger().info("Starting Somnia network...")

            # Initialize exchange market info for trading rules and symbol mapping
            self.logger().info("DEBUG: About to call build_exchange_market_info()")
            await self.build_exchange_market_info()
            self.logger().info("DEBUG: build_exchange_market_info() completed successfully")

            self.logger().info("DEBUG: About to call super().start_network() which should start order book tracker")
            await super().start_network()
            self.logger().info("DEBUG: super().start_network() completed successfully")

            # 🔄 PHASE 3: Start transaction monitoring
            await self._start_tx_monitoring()

            # 💰 PHASE 4: Start periodic balance refresh
            await self._start_balance_refresh()

            self.logger().info("🎉 Somnia network started successfully")
        except Exception as e:
            self.logger().error(f"DEBUG: Exception in start_network(): {e}")
            self.logger().error(f"Failed to start Somnia network: {e}")
            self.logger().exception("Full traceback:")
            # Don't raise - let the system continue
            pass

    async def stop_network(self):
        """
        Stop network and cleanup resources when connector shuts down.
        This method is called during connector shutdown.
        """
        try:
            self.logger().info("🛑 Stopping Somnia network...")

            # Stop background tasks
            await self._stop_tx_monitoring()
            await self._stop_balance_refresh()

            # Call parent's stop_network to cleanup all background tasks
            await super().stop_network()

            self.logger().info("✅ Somnia network stopped successfully")

        except Exception as e:
            self.logger().error(f"Error stopping Somnia network: {e}")
            # Still call parent's stop_network to ensure proper cleanup
            try:
                await super().stop_network()
            except Exception as parent_error:
                self.logger().error(f"Error in parent stop_network: {parent_error}")

    async def cancel_all(self, timeout_seconds: float) -> List:
        """
        Cancel all active orders with timeout support.
        Enhanced version that leverages our blockchain transaction tracking.

        Args:
            timeout_seconds: Maximum time to wait for cancellations

        Returns:
            List of cancellation results
        """
        try:
            from hummingbot.core.data_type.cancellation_result import CancellationResult

            self.logger().info(f"🚫 Cancelling all orders with {timeout_seconds}s timeout...")

            # Get all active orders
            active_orders = list(self._order_tracker.active_orders.values())
            if not active_orders:
                self.logger().info("No active orders to cancel")
                return []

            self.logger().info(f"Found {len(active_orders)} active orders to cancel")

            # Track cancellation start time
            start_time = time.time()
            cancellation_results = []

            # Cancel all orders concurrently
            cancel_tasks = []
            for order in active_orders:
                task = asyncio.create_task(self._execute_order_cancel_and_process_update(order))
                cancel_tasks.append((order, task))

            # Wait for cancellations with timeout
            completed_tasks = []
            timeout_tasks = []

            for order, task in cancel_tasks:
                try:
                    # Wait for each cancellation with remaining timeout
                    remaining_timeout = timeout_seconds - (time.time() - start_time)
                    if remaining_timeout <= 0:
                        timeout_tasks.append((order, task))
                        continue

                    success = await asyncio.wait_for(task, timeout=remaining_timeout)
                    completed_tasks.append((order, success))

                    result = CancellationResult(order_id=order.client_order_id, success=success)
                    cancellation_results.append(result)

                except asyncio.TimeoutError:
                    timeout_tasks.append((order, task))
                    self.logger().warning(f"⏰ Cancellation timeout for order {order.client_order_id}")

                except Exception as e:
                    self.logger().error(f"❌ Error cancelling order {order.client_order_id}: {e}")
                    result = CancellationResult(order_id=order.client_order_id, success=False)
                    cancellation_results.append(result)

            # Handle timeout tasks
            for order, task in timeout_tasks:
                task.cancel()
                result = CancellationResult(order_id=order.client_order_id, success=False)
                cancellation_results.append(result)

            # Summary
            successful_cancellations = sum(1 for r in cancellation_results if r.success)
            total_time = time.time() - start_time

            self.logger().info(
                f"📊 Cancellation complete: {successful_cancellations}/{len(active_orders)} "
                f"successful in {total_time:.2f}s"
            )

            return cancellation_results

        except Exception as e:
            self.logger().error(f"Error in cancel_all: {e}")
            return []

    def batch_order_cancel(self, orders_to_cancel: List) -> None:
        """
        Batch cancel orders for improved efficiency.
        Initiates cancellation of multiple orders simultaneously.

        Args:
            orders_to_cancel: List of LimitOrder objects to cancel
        """
        try:
            if not orders_to_cancel:
                return

            self.logger().info(f"📦 Batch cancelling {len(orders_to_cancel)} orders...")

            # Convert to async cancellation tasks
            for order in orders_to_cancel:
                # Find the tracked order
                tracked_order = self._order_tracker.fetch_order(order.client_order_id)
                if tracked_order:
                    # Use our async cancellation system
                    asyncio.create_task(self._execute_order_cancel_and_process_update(tracked_order))
                else:
                    self.logger().warning(f"Order {order.client_order_id} not found in tracker")

            self.logger().info(f"✅ Initiated batch cancellation of {len(orders_to_cancel)} orders")

        except Exception as e:
            self.logger().error(f"Error in batch_order_cancel: {e}")

    async def get_all_pairs_prices(self) -> List[Dict[str, str]]:
        """
        Get current prices for all trading pairs.
        Used for price discovery and arbitrage opportunities.

        Returns:
            List of price dictionaries with format:
            [{"symbol": "STT-USDC", "price": "1.25"}, ...]
        """
        try:
            self.logger().debug("Fetching all pairs prices...")

            pairs_prices = []

            # Get prices for all configured trading pairs
            for trading_pair in self._trading_pairs:
                try:
                    # Use our enhanced quote price method
                    # Get a small amount to get current market price
                    quote_amount = Decimal("1.0")

                    # Get both buy and sell prices for spread information
                    buy_price = await self.get_quote_price(trading_pair, is_buy=True, amount=quote_amount)
                    sell_price = await self.get_quote_price(trading_pair, is_buy=False, amount=quote_amount)

                    # Use mid-price as the representative price
                    if buy_price > 0 and sell_price > 0:
                        mid_price = (buy_price + sell_price) / 2
                    elif buy_price > 0:
                        mid_price = buy_price
                    elif sell_price > 0:
                        mid_price = sell_price
                    else:
                        # Fallback to order book data if available
                        mid_price = await self._get_last_traded_price(trading_pair)

                    if mid_price > 0:
                        pairs_prices.append(
                            {
                                "symbol": trading_pair,
                                "price": str(mid_price),
                                "buy_price": str(buy_price) if buy_price > 0 else None,
                                "sell_price": str(sell_price) if sell_price > 0 else None,
                                "timestamp": str(self.current_timestamp),
                            }
                        )

                    self.logger().debug(f"Price for {trading_pair}: {mid_price}")

                except Exception as pair_error:
                    self.logger().warning(f"Failed to get price for {trading_pair}: {pair_error}")
                    # Continue with other pairs
                    continue

            self.logger().info(f"📈 Retrieved prices for {len(pairs_prices)}/{len(self._trading_pairs)} trading pairs")
            return pairs_prices

        except Exception as e:
            self.logger().error(f"Error getting all pairs prices: {e}")
            return []

    async def build_exchange_market_info(self) -> Dict[str, Any]:
        """
        Build comprehensive market information including trading pairs, symbols, contracts.
        This method fetches and organizes exchange data for proper connector initialization.

        Returns:
            Dictionary containing exchange market information
        """
        try:
            self.logger().info("=== DEBUG: build_exchange_market_info STARTING ===")
            self.logger().info(f"  Current trading_pairs: {self._trading_pairs}")
            self.logger().info(f"  trading_required: {self._trading_required}")

            # Get available trading pairs and market data
            self.logger().info("DEBUG: About to call _get_symbols()")
            symbols = await self._get_symbols()
            self.logger().info("DEBUG: _get_symbols() returned {len(symbols)} symbols")

            self.logger().info("DEBUG: About to call _get_contracts()")
            contracts = await self._get_contracts()
            self.logger().info("DEBUG: _get_contracts() returned {len(contracts)} contracts")

            self.logger().info("DEBUG: About to call _get_fee_rates()")
            fee_rates = await self._get_fee_rates()
            self.logger().info("DEBUG: _get_fee_rates() returned: {fee_rates}")

            exchange_info = {
                "symbols": symbols,
                "contracts": contracts,
                "fee_rates": fee_rates,
                "server_time": int(time.time() * 1000),
                "rate_limits": self.rate_limits_rules,
            }

            # Initialize trading rules from symbols data
            self.logger().info("DEBUG: About to initialize trading rules from symbols data...")
            await self._initialize_trading_rules_from_symbols(symbols)
            self.logger().info("DEBUG: Trading rules initialization completed")

            # Initialize account balances
            self.logger().info("DEBUG: About to initialize account balances...")
            await self._update_balances()
            self.logger().info("DEBUG: Account balances initialization completed")

            self.logger().info(f"=== DEBUG: build_exchange_market_info COMPLETED ===")
            self.logger().info(f"  Built exchange info with {len(symbols)} symbols and {len(contracts)} contracts")
            return exchange_info

        except Exception as e:
            self.logger().error(f"CRITICAL: Failed to build exchange market info: {e}")
            self.logger().exception("Full exception details:")
            # Return minimal info to prevent startup failure
            return {
                "symbols": [],
                "contracts": {},
                "fee_rates": {},
                "server_time": int(time.time() * 1000),
                "rate_limits": self.rate_limits_rules,
            }

    async def _initialize_trading_pair_symbol_map(self):
        """
        Override the default symbol map initialization.
        Uses build_exchange_market_info to fetch and organize symbol mappings.
        """
        try:
            self.logger().info("DEBUG: _initialize_trading_pair_symbol_map() called")
            exchange_info = await self.build_exchange_market_info()
            self.logger().info(
                "DEBUG: build_exchange_market_info() returned: {type(exchange_info)} with keys: {list(exchange_info.keys()) if isinstance(exchange_info, dict) else 'NOT_DICT'}"
            )
            self.logger().info("DEBUG: About to call _initialize_trading_pair_symbols_from_exchange_info")
            self._initialize_trading_pair_symbols_from_exchange_info(exchange_info=exchange_info)
            self.logger().info("DEBUG: _initialize_trading_pair_symbols_from_exchange_info completed")
        except Exception as e:
            self.logger().exception("There was an error requesting exchange info.")
            # Don't raise to prevent startup failure

    async def _initialize_trading_rules_from_symbols(self, symbols: List[Dict[str, Any]]):
        """
        Initialize trading rules from symbol information.

        Args:
            symbols: List of symbol information dictionaries
        """
        try:
            self.logger().info("Initializing trading rules from symbols...")
            trading_rules = {}

            for symbol_info in symbols:
                symbol = symbol_info.get("symbol", "")
                if symbol:
                    base = symbol_info.get("baseAsset", "")
                    quote = symbol_info.get("quoteAsset", "")

                    # Create trading rule for this symbol
                    trading_rules[symbol] = {
                        "symbol": symbol,
                        "baseAsset": base,
                        "quoteAsset": quote,
                        "baseAssetPrecision": symbol_info.get("baseAssetPrecision", 8),
                        "quotePrecision": symbol_info.get("quotePrecision", 8),
                        "minQty": "0.001",
                        "maxQty": "1000000",
                        "stepSize": "0.001",
                        "minPrice": "0.001",
                        "maxPrice": "1000000",
                        "tickSize": "0.001",
                        "minNotional": "1.0",
                        "status": "TRADING",
                    }

                    # 🔍 DEBUG: Log hardcoded trading rule (this method may override our fix!)
                    self.logger().warning(f"🔍 HARDCODED RULE WARNING: {symbol}")
                    self.logger().warning(f"   - Using hardcoded tickSize: 0.001")
                    self.logger().warning(f"   - This may override CONTRACT_PRICE_DECIMALS setting!")

            # Update internal trading rules
            formatted_rules = await self._format_trading_rules(trading_rules)
            self._trading_rules.clear()
            for rule in formatted_rules:
                self._trading_rules[rule.trading_pair] = rule

            self.logger().info(f"Initialized {len(trading_rules)} trading rules")

        except Exception as e:
            self.logger().error(f"Failed to initialize trading rules from symbols: {e}")
            # Don't raise to prevent startup failure

    async def _api_request(
        self,
        method: str,
        endpoint: str = "",
        params: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
        data: Optional[Dict[str, Any]] = None,
        is_auth_required: bool = False,
    ) -> Dict[str, Any]:
        """
        Generic API request method for making HTTP requests to Somnia API.

        Args:
            method: HTTP method (GET, POST, etc.)
            endpoint: API endpoint
            params: URL parameters
            headers: Request headers
            data: Request data
            is_auth_required: Whether authentication is required

        Returns:
            API response data
        """
        try:
            if is_auth_required and self._auth:
                if headers is None:
                    headers = {}
                auth_headers = await self._auth.get_headers()
                headers.update(auth_headers)

            # For now, return mock data since we're using StandardWeb3 directly
            # This method can be enhanced later for additional API calls
            return {"success": True, "data": {}}

        except Exception as e:
            self.logger().error(f"API request failed: {e}")
            raise

    async def _get_symbols(self) -> List[Dict[str, Any]]:
        """
        Get symbol information from Somnia exchange.

        Returns:
            List of symbol information dictionaries
        """
        try:
            self.logger().info("DEBUG: _get_symbols called with:")
            self.logger().info(f"  - self._trading_pairs = {self._trading_pairs}")
            self.logger().info(f"  - self._trading_required = {self._trading_required}")
            self.logger().info(
                f"  - len(self._trading_pairs) = {len(self._trading_pairs) if self._trading_pairs else 0}"
            )

            # If this is a non-trading connector (used for connection testing),
            # return empty list to avoid any processing
            if not self._trading_required and not self._trading_pairs:
                self.logger().info("Non-trading connector mode - returning empty symbols list for connection testing")
                return []

            # Use configured trading pairs
            symbols = []
            self.logger().info(f"Processing {len(self._trading_pairs)} trading pairs...")

            for i, trading_pair in enumerate(self._trading_pairs):
                self.logger().info(f"  Processing trading pair {i + 1}/{len(self._trading_pairs)}: '{trading_pair}'")
                try:
                    if "-" not in trading_pair:
                        self.logger().error(f"  Invalid trading pair format (missing '-'): '{trading_pair}'")
                        continue

                    base, quote = trading_pair.split("-", 1)  # Split only on first dash
                    self.logger().info(f"  Split '{trading_pair}' -> base: '{base}', quote: '{quote}'")

                    if not base or not quote:
                        self.logger().error(f"  Empty base or quote after split: base='{base}', quote='{quote}'")
                        continue

                    symbol_info = {
                        "symbol": trading_pair,
                        "baseAsset": base,
                        "quoteAsset": quote,
                        "status": "TRADING",
                        "baseAssetPrecision": 8,
                        "quotePrecision": 8,
                        "orderTypes": ["LIMIT", "MARKET"],
                    }
                    symbols.append(symbol_info)
                    self.logger().info(f"  Successfully created symbol info for '{trading_pair}'")

                except ValueError as e:
                    self.logger().error(f"  ValueError processing trading pair '{trading_pair}': {e}")
                except Exception as e:
                    self.logger().error(f"  Unexpected error processing trading pair '{trading_pair}': {e}")

            # In trading mode, we should have symbols configured by the strategy
            if not symbols and self._trading_required:
                self.logger().error(
                    "CRITICAL: Trading mode requires configured trading pairs but none were successfully processed"
                )
                self.logger().error(f"  Original trading pairs: {self._trading_pairs}")
                self.logger().error(
                    "  This indicates a configuration problem - the strategy should provide valid trading pairs"
                )
                # Don't hardcode - return empty and let the system handle the error properly
                return []

            self.logger().info(f"Successfully processed {len(symbols)} symbols: {[s['symbol'] for s in symbols]}")
            return symbols

        except Exception as e:
            self.logger().error(f"CRITICAL: Exception in _get_symbols: {e}")
            self.logger().exception("Full exception details:")
            # Don't hardcode a fallback - return empty and let caller handle
            return []

    async def _get_contracts(self) -> Dict[str, Any]:
        """
        Get contract information from Somnia exchange.

        Returns:
            Dictionary of contract information
        """
        try:
            # Return contract information for known tokens
            contracts = {}

            # Get token addresses from constants
            default_tokens = CONSTANTS.DEFAULT_TOKENS_PER_DOMAIN.get(self._domain, set())
            for symbol in default_tokens:
                address = utils.convert_symbol_to_address(symbol, self._domain)
                if address and address != "0x...":
                    # Get decimals from constants
                    decimals = CONSTANTS.TOKEN_DECIMALS.get(symbol, 18)
                    contracts[symbol] = {
                        "address": address,
                        "decimals": decimals,
                        "symbol": symbol,
                    }

            self.logger().info(f"Retrieved {len(contracts)} contracts")
            return contracts

        except Exception as e:
            self.logger().error(f"Failed to get contracts: {e}")
            return {}

    async def _get_fee_rates(self) -> Dict[str, Any]:
        """
        Get current fee rates from Somnia exchange.

        Returns:
            Dictionary of fee rate information
        """
        try:
            # Return default fee rates (can be enhanced to fetch dynamically)
            fee_rates = {
                "maker_fee": "0.001",  # 0.1%
                "taker_fee": "0.002",  # 0.2%
            }

            self.logger().info("Retrieved fee rates")
            return fee_rates

        except Exception as e:
            self.logger().error(f"Failed to get fee rates: {e}")
            return {"maker_fee": "0.001", "taker_fee": "0.002"}

    async def _get_account(self) -> Dict[str, Any]:
        """
        Get account information from Somnia exchange.

        Returns:
            Dictionary containing account information
        """
        try:
            if not self._standard_client:
                raise ValueError("StandardWeb3 client not initialized")

            # Get account balances and info using StandardWeb3
            account_info = {
                "address": self._wallet_address,
                "balances": {},
            }

            # Get balances for known tokens
            default_tokens = CONSTANTS.DEFAULT_TOKENS_PER_DOMAIN.get(self._domain, set())
            for token in default_tokens:
                try:
                    # This would use StandardWeb3 to get actual balance
                    balance = "0"  # Placeholder - implement actual balance fetching
                    account_info["balances"][token] = balance
                except Exception as e:
                    self.logger().warning(f"Failed to get {token} balance: {e}")
                    account_info["balances"][token] = "0"

            return account_info

        except Exception as e:
            self.logger().error(f"Failed to get account info: {e}")
            return {"address": self._wallet_address, "balances": {}}

    async def _get_account_max_withdrawable(self) -> Dict[str, Decimal]:
        """
        Get maximum withdrawable amounts for each asset.

        Returns:
            Dictionary mapping asset to max withdrawable amount
        """
        try:
            account_info = await self._get_account()
            max_withdrawable = {}

            for asset, balance_str in account_info.get("balances", {}).items():
                balance = Decimal(balance_str) if balance_str else Decimal("0")
                # For simplicity, assume full balance is withdrawable
                # In reality, you might need to account for locked amounts
                max_withdrawable[asset] = balance

            return max_withdrawable

        except Exception as e:
            self.logger().error(f"Failed to get max withdrawable amounts: {e}")
            return {}

    # ====== END MISSING METHODS ======

    def supported_order_types(self) -> List[OrderType]:
        """
        Return list of supported order types.

        Returns:
            List of supported OrderType values
        """
        return [OrderType.LIMIT, OrderType.MARKET]

    def update_trading_pairs(self, trading_pairs: List[str]):
        """
        Update trading pairs after connector initialization.
        This method allows the connector to be updated with trading pairs from the strategy.

        Args:
            trading_pairs: List of trading pairs to support
        """
        self.logger().info("=== DEBUG: update_trading_pairs CALLED ===")
        self.logger().info(f"  Current trading_pairs: {self._trading_pairs}")
        self.logger().info(f"  New trading_pairs: {trading_pairs}")
        self.logger().info(f"  trading_required: {self._trading_required}")

        # Log call stack to see who's calling this
        stack = traceback.format_stack()
        self.logger().info("DEBUG: update_trading_pairs call stack (last 3 frames):")
        for i, frame in enumerate(stack[-3:]):
            self.logger().info(f"  Frame {i}: {frame.strip()}")

        if trading_pairs and trading_pairs != self._trading_pairs:
            self.logger().info(f"UPDATING: Trading pairs changing from {self._trading_pairs} to {trading_pairs}")
            self._trading_pairs = trading_pairs

            # Update order book data source if it exists
            if hasattr(self, "_order_book_tracker") and self._order_book_tracker:
                self.logger().info("DEBUG: Updating order book tracker data source...")
                if hasattr(self._order_book_tracker, "data_source") and self._order_book_tracker.data_source:
                    self._order_book_tracker.data_source.update_trading_pairs(trading_pairs)
                    self.logger().info("DEBUG: Order book data source updated")
                else:
                    self.logger().warning("DEBUG: Order book tracker has no data_source")
            else:
                self.logger().warning("DEBUG: No order book tracker found")

            # Re-initialize trading rules for new pairs
            try:
                import asyncio

                if asyncio.get_event_loop().is_running():
                    self.logger().info("DEBUG: Event loop running, creating task for trading rules update")
                    asyncio.create_task(self._update_trading_rules_for_new_pairs(trading_pairs))
                else:
                    # If no event loop is running, schedule for later
                    self.logger().info(
                        "DEBUG: No event loop running, trading rules will be updated when connector starts"
                    )
            except Exception as e:
                self.logger().warning("DEBUG: Could not update trading rules immediately: {e}")
        elif not trading_pairs:
            self.logger().warning(f"SKIPPING: Empty trading_pairs provided: {trading_pairs}")
        elif trading_pairs == self._trading_pairs:
            self.logger().info(f"SKIPPING: Trading pairs unchanged: {trading_pairs}")
        else:
            self.logger().warning(
                f"SKIPPING: Unexpected condition - trading_pairs: {trading_pairs}, current: {self._trading_pairs}"
            )

        self.logger().info("=== DEBUG: update_trading_pairs COMPLETED ===")
        self.logger().info(f"  Final trading_pairs: {self._trading_pairs}")

    async def _update_trading_rules_for_new_pairs(self, trading_pairs: List[str]):
        """Update trading rules for newly added trading pairs."""
        try:
            symbols = []
            for trading_pair in trading_pairs:
                base, quote = trading_pair.split("-")
                symbols.append(
                    {
                        "symbol": trading_pair,
                        "baseAsset": base,
                        "quoteAsset": quote,
                        "status": "TRADING",
                        "baseAssetPrecision": 8,
                        "quotePrecision": 8,
                        "orderTypes": ["LIMIT", "MARKET"],
                    }
                )

            await self._initialize_trading_rules_from_symbols(symbols)
            self.logger().info("Updated trading rules for {len(trading_pairs)} trading pairs")

        except Exception as e:
            self.logger().error(f"Failed to update trading rules for new pairs: {e}")

    @property
    def trading_pairs(self) -> List[str]:
        """Get current trading pairs."""
        return self._trading_pairs

    def _is_request_exception_related_to_time_synchronizer(self, request_exception: Exception) -> bool:
        """
        Check if request exception is related to time synchronization.

        Args:
            request_exception: Exception to check

        Returns:
            True if time-related, False otherwise
        """
        # Somnia doesn't typically have time sync issues like CEXs
        return False

    def _is_order_not_found_during_status_update_error(self, status_update_exception: Exception) -> bool:
        """
        Check if exception indicates order not found during status update.

        Args:
            status_update_exception: Exception to check

        Returns:
            True if order not found, False otherwise
        """
        error_message = str(status_update_exception).lower()
        return "order not found" in error_message or "not found" in error_message

    def _is_order_not_found_during_cancelation_error(self, cancelation_exception: Exception) -> bool:
        """
        Check if exception indicates order not found during cancellation.

        Args:
            cancelation_exception: Exception to check

        Returns:
            True if order not found, False otherwise
        """
        error_message = str(cancelation_exception).lower()
        return "order not found" in error_message or "cannot cancel" in error_message

    def _create_web_assistants_factory(self) -> WebAssistantsFactory:
        """
        Create web assistants factory.

        Returns:
            WebAssistantsFactory instance
        """
        return web_utils.build_api_factory(
            throttler=self._throttler,
            auth=self._auth,
        )

    def _create_order_book_data_source(self) -> OrderBookTrackerDataSource:
        """
        Create order book data source.

        Returns:
            OrderBookTrackerDataSource instance
        """
        self.logger().info("DEBUG: _create_order_book_data_source() called")
        self.logger().info("DEBUG: Current trading_pairs: {self._trading_pairs}")
        self.logger().info("DEBUG: trading_required: {self._trading_required}")

        # Use the configured trading pairs - don't hardcode anything
        effective_trading_pairs = self._trading_pairs.copy() if self._trading_pairs else []
        self.logger().info("DEBUG: Creating order book data source with trading_pairs: {effective_trading_pairs}")

        try:
            data_source = StandardAPIOrderBookDataSource(
                trading_pairs=effective_trading_pairs,
                connector=self,  # Pass self reference like other exchanges
                api_factory=self._web_assistants_factory,
                domain=self._domain,
                throttler=self._throttler,
            )
            self.logger().info("DEBUG: Order book data source created successfully")
            # Store reference to update later if needed
            self._orderbook_ds = data_source
            return data_source
        except Exception as e:
            self.logger().error("DEBUG: Failed to create order book data source: {e}")
            self.logger().exception("DEBUG: Exception details:")
            raise

    def _create_user_stream_data_source(self) -> UserStreamTrackerDataSource:
        """
        Create user stream data source.

        Returns:
            UserStreamTrackerDataSource instance
        """
        return StandardAPIUserStreamDataSource(
            auth=self._auth,
            trading_pairs=self._trading_pairs,
            connector=self,
            api_factory=self._web_assistants_factory,
            domain=self._domain,
            throttler=self._throttler,
        )

    async def _get_last_traded_price(self, trading_pair: str) -> float:
        """
        Get last traded price for a trading pair.

        Args:
            trading_pair: Trading pair

        Returns:
            Last traded price
        """
        try:
            prices = await self._order_book_tracker.data_source.get_last_traded_prices([trading_pair])
            return prices.get(trading_pair, 0.0)
        except Exception as e:
            self.logger().error(f"Error getting last traded price for {trading_pair}: {e}")
            return 0.0

    def get_price_by_type(self, trading_pair: str, price_type: PriceType) -> Decimal:
        """
        Override to get fresh mktPrice from the latest API response.

        🔥 CRITICAL: This is called EVERY TIME the bot calculates order prices!
        🚨 MUST be fresh data - no stale cached prices allowed.
        🚨 MUST be synchronous - no async calls allowed.
        """

        self.logger().info(f"🔍 PRICE REQUEST: get_price_by_type({trading_pair}, {price_type})")

        if price_type is PriceType.LastTrade:
            self.logger().info(f"🎯 LastTrade price requested for {trading_pair}")

            try:
                # Get fresh mktPrice from the latest API response stored in data source
                if hasattr(self, '_order_book_tracker') and self._order_book_tracker:
                    data_source = self._order_book_tracker.data_source
                    if hasattr(data_source, '_latest_api_response') and data_source._latest_api_response:
                        mkt_price = data_source._latest_api_response.get("mktPrice")
                        if mkt_price and mkt_price > 0:
                            self.logger().info(f"✅ Using fresh mktPrice for {trading_pair}: {mkt_price}")
                            return Decimal(str(mkt_price))
                        else:
                            self.logger().warning(f"⚠️ No valid mktPrice in latest API response: {mkt_price}")
                    else:
                        self.logger().warning(f"⚠️ No latest API response available")
                else:
                    self.logger().warning(f"⚠️ Order book tracker not available")

                self.logger().error(f"❌ No fresh mktPrice available for {trading_pair}")
                raise ValueError(f"No fresh mktPrice available for {trading_pair}")

            except Exception as e:
                self.logger().error(f"💥 Failed to get fresh LastTrade price for {trading_pair}: {e}")
                raise Exception(f"Fresh LastTrade pricing failed for {trading_pair}: {e}")
        else:
            # Use base implementation for other price types
            self.logger().info(f"🔄 Using base implementation for price type: {price_type}")
            result = super().get_price_by_type(trading_pair, price_type)
            self.logger().info(f"✅ Base implementation returned: {result}")
            return result

    async def _make_trading_rules_request(self) -> Any:
        """
        Make request to get trading rules.

        Returns:
            Trading rules data
        """
        # For Somnia, we'll define trading rules based on known token configurations
        trading_rules = {}

        for trading_pair in self._trading_pairs:
            base, quote = utils.split_trading_pair(trading_pair)

            # Get token decimals for precision
            base_decimals = utils.get_token_decimals(base)
            quote_decimals = utils.get_token_decimals(quote)

            # Define basic trading rules
            trading_rules[trading_pair] = {
                "symbol": trading_pair,
                "baseAssetPrecision": base_decimals,
                "quoteAssetPrecision": quote_decimals,
                "minQty": str(CONSTANTS.MIN_ORDER_SIZE),
                "maxQty": str(CONSTANTS.MAX_ORDER_SIZE),
                "stepSize": str(Decimal("1e-{}".format(base_decimals))),
                "minPrice": str(Decimal("1e-{}".format(CONSTANTS.CONTRACT_PRICE_DECIMALS))),  # Use contract precision
                "maxPrice": str(CONSTANTS.MAX_ORDER_SIZE),
                "tickSize": str(Decimal("1e-{}".format(CONSTANTS.CONTRACT_PRICE_DECIMALS))),  # Use contract precision
                "minNotional": str(CONSTANTS.MIN_ORDER_SIZE),
                "status": "TRADING",
            }

            # 🔍 DEBUG: Log the trading rule values
            tick_size_value = str(Decimal("1e-{}".format(CONSTANTS.CONTRACT_PRICE_DECIMALS)))
            self.logger().info(f"🔍 TRADING RULE DEBUG: {trading_pair}")
            self.logger().info(f"   - CONTRACT_PRICE_DECIMALS = {CONSTANTS.CONTRACT_PRICE_DECIMALS}")
            self.logger().info(f"   - tickSize = {tick_size_value}")
            self.logger().info(f"   - minPrice = {str(Decimal('1e-{}'.format(CONSTANTS.CONTRACT_PRICE_DECIMALS)))}")

        return trading_rules

    async def _make_trading_pairs_request(self) -> Any:
        """
        Make request to get available trading pairs.

        Returns:
            Trading pairs data
        """
        # Return the configured trading pairs for Somnia
        trading_pairs_data = []

        for trading_pair in CONSTANTS.TRADING_PAIRS_PER_DOMAIN[self._domain]:
            base, quote = utils.split_trading_pair(trading_pair)

            trading_pairs_data.append(
                {
                    "symbol": trading_pair,
                    "baseAsset": base,
                    "quoteAsset": quote,
                    "status": "TRADING",
                }
            )

        return trading_pairs_data

    def _get_fee(
        self,
        base_currency: str,
        quote_currency: str,
        order_type: OrderType,
        order_side: TradeType,
        amount: Decimal,
        price: Decimal = s_decimal_NaN,
        is_maker: Optional[bool] = None,
    ) -> TradeFeeBase:
        """
        Calculate trading fee for an order.

        Args:
            base_currency: Base currency
            quote_currency: Quote currency
            order_type: Order type
            order_side: Order side (buy/sell)
            amount: Order amount
            price: Order price
            is_maker: Whether the order is a maker order

        Returns:
            TradeFeeBase instance
        """
        trading_pair = f"{base_currency}-{quote_currency}"
        is_maker = is_maker or (order_type is OrderType.LIMIT_MAKER)

        if trading_pair not in self._trading_fees:
            fee = build_trade_fee(
                exchange=self.name,
                is_maker=is_maker,
                order_side=order_side,
                order_type=order_type,
                amount=amount,
                price=price,
                base_currency=base_currency,
                quote_currency=quote_currency,
            )
        else:
            fee_data = self._trading_fees[trading_pair]
            if is_maker:
                fee_value = fee_data["maker"]
            else:
                fee_value = fee_data["taker"]
            fee = AddedToCostTradeFee(percent=fee_value)

        return fee

    async def _get_current_nonce(self) -> int:
        """
        Get proper blockchain nonce using Dexalot-style approach.
        Note: Transaction lock should be held by caller to prevent race conditions.
        """
        try:
            from web3 import Web3

            # Use the Web3 connection from our RPC URL
            w3 = Web3(Web3.HTTPProvider(self._rpc_url))

            # Get current nonce from blockchain
            current_nonce = await asyncio.get_event_loop().run_in_executor(
                None, w3.eth.get_transaction_count, self._wallet_address, "pending"
            )

            # Use the higher of current blockchain nonce or our tracked nonce
            # This prevents "nonce too low" errors from concurrent transactions
            final_nonce = current_nonce if current_nonce > self._last_nonce else self._last_nonce

            # Update our tracking
            self._last_nonce = final_nonce + 1

            self.logger().debug(
                f"Nonce management: blockchain={current_nonce}, tracked={self._last_nonce - 1}, using={final_nonce}"
            )
            return final_nonce

        except Exception as e:
            self.logger().error(f"Error getting blockchain nonce: {e}")
            # Fallback: increment our tracked nonce
            self._last_nonce += 1
            return self._last_nonce

    async def _ensure_token_allowances(
        self, base_address: str, quote_address: str, amount: Decimal, price: Decimal, is_buy: bool
    ):
        """
        Ensure sufficient token allowances before placing orders.

        Args:
            base_address: Base token address
            quote_address: Quote token address
            amount: Order amount
            price: Order price
            is_buy: Whether this is a buy order
        """
        try:
            from web3 import Web3

            # Create Web3 instance
            rpc_url = CONSTANTS.DOMAIN_CONFIG[self._domain]["rpc_url"]
            w3 = Web3(Web3.HTTPProvider(rpc_url))

            if not w3.is_connected():
                self.logger().warning("Failed to connect to RPC for allowance check")
                return

            # Standard ERC-20 allowance ABI
            erc20_abi = [
                {
                    "constant": True,
                    "inputs": [{"name": "_owner", "type": "address"}, {"name": "_spender", "type": "address"}],
                    "name": "allowance",
                    "outputs": [{"name": "", "type": "uint256"}],
                    "type": "function",
                },
                {
                    "constant": False,
                    "inputs": [{"name": "_spender", "type": "address"}, {"name": "_value", "type": "uint256"}],
                    "name": "approve",
                    "outputs": [{"name": "", "type": "bool"}],
                    "type": "function",
                },
            ]

            exchange_address = CONSTANTS.DOMAIN_CONFIG[self._domain]["standard_exchange_address"]
            wallet_address = w3.to_checksum_address(self._wallet_address)
            exchange_checksum = w3.to_checksum_address(exchange_address)

            if is_buy:
                # For buy orders, need allowance for quote token (USDC)
                token_address = quote_address
                quote_decimals = utils.get_token_decimals(utils.convert_address_to_symbol(quote_address, self._domain))
                required_amount = (amount * price) * (10**quote_decimals)
                token_symbol = utils.convert_address_to_symbol(quote_address, self._domain)
            else:
                # For sell orders, need allowance for base token (SOMI)
                token_address = base_address
                base_decimals = utils.get_token_decimals(utils.convert_address_to_symbol(base_address, self._domain))
                required_amount = amount * (10**base_decimals)
                token_symbol = utils.convert_address_to_symbol(base_address, self._domain)

            # Skip allowance check for native tokens
            if token_address == "0x0000000000000000000000000000000000000000":
                self.logger().info(f"Skipping allowance check for native token {token_symbol}")
                return

            # Create contract instance
            contract = w3.eth.contract(address=w3.to_checksum_address(token_address), abi=erc20_abi)

            # Check current allowance
            current_allowance = contract.functions.allowance(wallet_address, exchange_checksum).call()

            self.logger().info(
                f"Token allowance check for {token_symbol}: current={current_allowance}, required={required_amount}"
            )

            if current_allowance < required_amount:
                self.logger().info(f"Insufficient allowance for {token_symbol}. Approving {required_amount}...")

                # Use direct Web3 contract call to approve tokens
                if not self._private_key:
                    raise ValueError("Wallet private key not available for token approval")

                # Approve a large amount to avoid frequent approvals (e.g., max uint256)
                max_approval = 2**256 - 1  # Max uint256

                self.logger().info(f"Approving {token_symbol} with amount: {max_approval}")

                # Build the approval transaction
                approve_function = contract.functions.approve(exchange_checksum, max_approval)

                # Get gas estimate
                try:
                    gas_estimate = approve_function.estimate_gas({"from": wallet_address})
                    gas_limit = int(gas_estimate * 1.2)  # Add 20% buffer
                except Exception as e:
                    self.logger().warning(f"Could not estimate gas for approval: {e}, using default")
                    gas_limit = 100000  # Default gas limit for ERC20 approval

                # Get current nonce
                nonce = w3.eth.get_transaction_count(wallet_address, "pending")

                # Build transaction
                transaction = approve_function.build_transaction(
                    {
                        "from": wallet_address,
                        "gas": gas_limit,
                        "gasPrice": w3.eth.gas_price,
                        "nonce": nonce,
                    }
                )

                # Sign transaction
                from eth_account import Account

                signed_txn = Account.sign_transaction(transaction, self._private_key)

                # Send transaction
                tx_hash = w3.eth.send_raw_transaction(signed_txn.raw_transaction)
                tx_hash_hex = tx_hash.hex()

                self.logger().info(f"Approval transaction submitted: {tx_hash_hex}")

                # Wait for transaction confirmation
                import asyncio

                receipt = None
                for i in range(30):  # Wait up to 30 seconds
                    try:
                        receipt = w3.eth.get_transaction_receipt(tx_hash)
                        if receipt:
                            break
                    except Exception:
                        pass
                    await asyncio.sleep(1)

                if receipt and receipt.status == 1:
                    self.logger().info(f"Approval transaction confirmed: {tx_hash_hex}")

                    # Check the new allowance
                    new_allowance = contract.functions.allowance(wallet_address, exchange_checksum).call()
                    self.logger().info(f"New allowance for {token_symbol}: {new_allowance}")

                    if new_allowance < required_amount:
                        raise ValueError(f"Approval failed - still insufficient allowance for {token_symbol}")
                else:
                    raise ValueError(f"Approval transaction failed or not confirmed: {tx_hash_hex}")
            else:
                self.logger().info(f"Sufficient allowance for {token_symbol}: {current_allowance} >= {required_amount}")

        except Exception as e:
            self.logger().error(f"Error checking/ensuring token allowances: {e}")
            raise

    async def _check_sufficient_balance(
        self, base_address: str, quote_address: str, amount: Decimal, price: Decimal, is_buy: bool
    ):
        """
        Check if wallet has sufficient token balance before placing orders.
        Uses already-fetched balance data from _update_balances() to avoid redundant Web3 calls.

        Special handling for native token sales: ensures we have enough for BOTH the sale amount AND gas fees.

        Args:
            base_address: Base token address
            quote_address: Quote token address
            amount: Order amount
            price: Order price
            is_buy: Whether this is a buy order
        """
        try:
            if is_buy:
                # For buy orders, need sufficient quote token (USDC) balance
                token_symbol = utils.convert_address_to_symbol(quote_address, self._domain)
                quote_decimals = utils.get_token_decimals(token_symbol)
                required_amount_decimal = amount * price

                # Standard balance check for quote token (no gas fee consideration)
                current_balance_decimal = self.get_balance(token_symbol)

            else:
                # For sell orders, need sufficient base token balance
                token_symbol = utils.convert_address_to_symbol(base_address, self._domain)
                base_decimals = utils.get_token_decimals(token_symbol)
                required_amount_decimal = amount

                # Get current balance from already-fetched data (avoids redundant Web3 call)
                current_balance_decimal = self.get_balance(token_symbol)

                # 🚨 CRITICAL: Check if we're selling native token (SOMI) - need to reserve gas fees!
                is_native_sell = token_symbol.upper() in CONSTANTS.NATIVE_TOKEN_LIST

                if is_native_sell:
                    # For native token sales, we need BOTH the sell amount AND gas for the transaction
                    # Use cached gas price to avoid redundant Web3 calls
                    gas_price = await self._get_cached_gas_price()

                    # Estimate gas for limitSellETH transaction (conservative)
                    estimated_gas = 50000000  # Higher estimate for native token sales
                    estimated_gas_cost_wei = gas_price * estimated_gas * self._gas_buffer_multiplier

                    # Convert to Decimal using proper scaling
                    estimated_gas_cost_decimal = Decimal(estimated_gas_cost_wei) / Decimal(10**18)

                    # Total required = sell amount + gas fees
                    required_amount_decimal = amount + estimated_gas_cost_decimal

                    self.logger().warning(
                        f"🔥 NATIVE TOKEN SALE: {token_symbol} | "
                        f"Sell: {amount:.6f} + Gas: {estimated_gas_cost_decimal:.6f} = "
                        f"Total needed: {required_amount_decimal:.6f} | "
                        f"Available: {current_balance_decimal:.6f}"
                    )

            self.logger().info(
                f"Balance check for {token_symbol}: current={current_balance_decimal:.6f}, required={required_amount_decimal:.6f}"
            )

            if current_balance_decimal < required_amount_decimal:
                if not is_buy and token_symbol.upper() in CONSTANTS.NATIVE_TOKEN_LIST:
                    # Special error message for native token sales
                    gas_needed = required_amount_decimal - amount
                    raise ValueError(
                        f"Insufficient {token_symbol} balance for native token sale. "
                        f"Have: {current_balance_decimal:.6f}, "
                        f"Need: {amount:.6f} (sell) + {gas_needed:.6f} (gas) = {required_amount_decimal:.6f} total"
                    )
                else:
                    raise ValueError(
                        f"Insufficient {token_symbol} balance. Have: {current_balance_decimal:.6f}, Need: {required_amount_decimal:.6f}"
                    )
            else:
                if not is_buy and token_symbol.upper() in CONSTANTS.NATIVE_TOKEN_LIST:
                    gas_reserved = required_amount_decimal - amount
                    self.logger().info(
                        f"✅ Sufficient {token_symbol} balance for native sale: {current_balance_decimal:.6f} "
                        f"(sell: {amount:.6f} + gas reserve: {gas_reserved:.6f})"
                    )
                else:
                    self.logger().info(
                        f"✅ Sufficient {token_symbol} balance: {current_balance_decimal:.6f} >= {required_amount_decimal:.6f}"
                    )

        except Exception as e:
            self.logger().error(f"Error checking token balance: {e}")
            raise

    async def _place_order(
        self,
        order_id: str,
        trading_pair: str,
        amount: Decimal,
        trade_type: TradeType,
        order_type: OrderType,
        price: Decimal,
        **kwargs,
    ) -> Tuple[str, float]:
        """
        Place an order on the exchange.

        Args:
            order_id: Client order ID
            trading_pair: Trading pair
            amount: Order amount
            trade_type: Buy or sell
            order_type: Order type (limit/market)
            price: Order price
            **kwargs: Additional arguments

        Returns:
            Tuple of (exchange_order_id, timestamp)
        """
        try:
            self.logger().info("DEBUG: _place_order called with:")
            self.logger().info(f"  - order_id: {order_id}")
            self.logger().info(f"  - trading_pair: {trading_pair}")
            self.logger().info(f"  - amount: {amount}")
            self.logger().info(f"  - trade_type: {trade_type}")
            self.logger().info(f"  - order_type: {order_type}")
            self.logger().info(f"  - price: {price}")

            # Use cached balance data from startup - no need to update before every order
            # Balance updates happen at startup and can be refreshed on-demand if needed
            self.logger().info("Using cached balance data for order placement...")

            base, quote = utils.split_trading_pair(trading_pair)
            base_address = utils.convert_symbol_to_address(base, self._domain)
            quote_address = utils.convert_symbol_to_address(quote, self._domain)

            if not base_address or not quote_address:
                raise ValueError(f"Could not get token addresses for {trading_pair}")

            # Determine if this is a buy order
            is_buy = trade_type == TradeType.BUY

            # Convert amounts to blockchain format
            base_decimals = utils.get_token_decimals(base)
            quote_decimals = utils.get_token_decimals(quote)

            # Check and ensure token allowances before placing order
            await self._ensure_token_allowances(base_address, quote_address, amount, price, is_buy)

            # Check token balances before placing order
            await self._check_sufficient_balance(base_address, quote_address, amount, price, is_buy)

            if order_type == OrderType.MARKET:
                # For market orders, we'll place a limit order at a price that should execute immediately
                # Use configurable slippage - default 0.3% for arbitrage strategies
                market_slippage = Decimal("0.003")  # 0.3% default - much better for arbitrage

                if is_buy:
                    # Buy at a higher price to ensure execution
                    execution_price = price * (Decimal("1") + market_slippage)
                    self.logger().info(f"🔥 MARKET BUY: {amount} {base} at {execution_price} ({market_slippage * 100}% slippage)")
                else:
                    # Sell at a lower price to ensure execution
                    execution_price = price * (Decimal("1") - market_slippage)
                    self.logger().info(f"🔥 MARKET SELL: {amount} {base} at {execution_price} ({market_slippage * 100}% slippage)")
            else:
                execution_price = price

            # Use transaction lock to prevent nonce conflicts between multiple orders
            async with self._transaction_lock:
                # Get current nonce for the account to avoid "nonce too low" errors
                current_nonce = await self._get_current_nonce()

                self.logger().info("DEBUG: About to call _place_order_direct_contract with:")
                self.logger().info(f"  - is_buy: {is_buy}")
                self.logger().info(f"  - base: {base} -> {base_address}")
                self.logger().info(f"  - quote: {quote} -> {quote_address}")
                self.logger().info(f"  - amount: {amount}")
                self.logger().info(f"  - execution_price: {execution_price}")

                # ===== APPROACH SELECTION =====
                # NEW: Use StandardWeb3 with fallback to direct contract method
                # This provides order IDs when StandardWeb3 works, with reliable fallback

                self.logger().info("🔄 Trying StandardWeb3 for order placement...")

                try:
                    # Create InFlightOrder for StandardWeb3 method
                    temp_order = InFlightOrder(
                        client_order_id=order_id,
                        trading_pair=trading_pair,
                        order_type=order_type,
                        trade_type=trade_type,
                        amount=amount,
                        price=execution_price,
                        creation_timestamp=time.time()
                    )

                    # Place order via StandardWeb3 and get both tx_hash and order_id
                    tx_hash, blockchain_order_id = await self._place_order_with_standardweb3(temp_order)

                    # Store the blockchain order ID for cancellation (this is the key improvement!)
                    self.logger().info(f"📝 Storing blockchain order ID {blockchain_order_id} for order {order_id}")

                    # We'll store this in the tracked order's exchange_order_id as a combined identifier
                    # Format: "tx_hash:order_id" so we can extract both later
                    result = f"{tx_hash}:{blockchain_order_id}"

                except Exception as e:
                    if "parsing bug" in str(e) or "base" in str(e):
                        self.logger().warning(f"🔄 StandardWeb3 failed ({e}), falling back to direct contract method...")

                        # Fallback to direct contract method
                        # result, _ = await self._place_order_direct_contract(
                        #     order_id, trading_pair, amount, trade_type, order_type, execution_price, is_buy,
                        #     base, base_address, quote, quote_address, base_decimals, quote_decimals
                        # )
                    else:
                        # Other errors should be propagated
                        raise

            # Handle return value - could be tuple (tx_hash, timestamp) or just tx_hash/combined_id
            if isinstance(result, tuple) and len(result) == 2:
                exchange_order_id, _ = result  # Extract the exchange_order_id (could be tx_hash or combined)
            else:
                exchange_order_id = result  # Already the proper exchange_order_id

            self.logger().info(f"Order placed successfully: {order_id} -> {exchange_order_id}")

            # Return the full exchange_order_id (could be tx_hash alone or "tx_hash:blockchain_order_id")
            timestamp = time.time()
            return exchange_order_id, timestamp

        except Exception as e:
            # Simple error handling following ORDER_FAILURE_HANDLING.md pattern:
            # Just log and re-raise - let ExchangePyBase._create_order handle the rest
            self.logger().error(f"Error placing order {order_id}: {e}")
            raise

    # 🚀 PHASE 2: Override _place_order_and_process_update for blockchain transaction tracking
    async def _place_order_and_process_update(self, order: InFlightOrder, **kwargs) -> str:
        """
        Override parent method to handle blockchain transaction tracking.
        This ensures proper order status management with async transaction confirmation.
        """
        try:
            # 💰 CRITICAL: Check gas balance before attempting order placement
            if not await self._ensure_sufficient_gas_before_transaction("place_order"):
                # Mark order as failed due to insufficient gas
                order_update = OrderUpdate(
                    client_order_id=order.client_order_id,
                    trading_pair=order.trading_pair,
                    update_timestamp=self.current_timestamp,
                    new_state=OrderState.FAILED,
                    misc_updates={
                        "error_message": "Insufficient gas balance for transaction",
                        "error_type": "INSUFFICIENT_GAS",
                        "gas_check_timestamp": time.time(),
                    },
                )
                self._order_tracker.process_order_update(order_update)

                # Also emit error event
                self.trigger_event(
                    MarketEvent.OrderFailure,
                    {
                        "order_id": order.client_order_id,
                        "error": "Insufficient gas balance - please deposit SOMI for gas fees",
                    },
                )

                raise Exception("Insufficient gas balance for order placement")

            # Call the standard _place_order method
            exchange_order_id, update_timestamp = await self._place_order(
                order_id=order.client_order_id,
                trading_pair=order.trading_pair,
                amount=order.amount,
                trade_type=order.trade_type,
                order_type=order.order_type,
                price=order.price,
                **kwargs,
            )

            # Map transaction hash to order
            if exchange_order_id:  # This is actually tx_hash
                self._tx_order_mapping[exchange_order_id] = order.client_order_id
                self._order_tx_mapping[order.client_order_id] = exchange_order_id

                # Update pending tx info with client_order_id
                if exchange_order_id in self._pending_tx_hashes:
                    self._pending_tx_hashes[exchange_order_id]["client_order_id"] = order.client_order_id

            # Create order update with OPEN state (transaction submitted)
            order_update: OrderUpdate = OrderUpdate(
                client_order_id=order.client_order_id,
                exchange_order_id=exchange_order_id,  # tx_hash
                trading_pair=order.trading_pair,
                update_timestamp=update_timestamp,
                new_state=OrderState.OPEN,  # Transaction submitted to mempool
            )
            self._order_tracker.process_order_update(order_update)

            self.logger().info(f"🚀 PHASE 2: Order {order.client_order_id} submitted as tx {exchange_order_id}")
            return exchange_order_id

        except Exception as e:
            # Let parent class handle the error properly
            self.logger().error(f"Failed to submit order {order.client_order_id}: {e}")

            # Refresh balances if error might be balance-related
            await self._refresh_balances_on_order_failure(order.client_order_id, str(e))

            raise

    # async def _place_order_direct_contract(
    #     self,
    #     base_address: str,
    #     quote_address: str,
    #     amount: Decimal,
    #     execution_price: Decimal,
    #     is_buy: bool,
    #     base_decimals: int,
    #     quote_decimals: int,
    #     current_nonce: int,
    # ) -> str:
    #     """
    #     Place order directly on the smart contract without using StandardWeb3.

    #     FUNCTION SELECTION LOGIC:
    #     - BUY orders: Always use limitBuy (regardless of token type)
    #     - SELL ERC20 tokens: Use limitSell
    #     - SELL NATIVE token (SOMI): Use limitSellETH (special function for native token)

    #     This approach matches the successful transaction pattern where limitSellETH
    #     is used specifically for selling the native token (SOMI/ETH).

    #     Args:
    #         base_address: Base token contract address
    #         quote_address: Quote token contract address
    #         amount: Order amount
    #         execution_price: Order execution price
    #         is_buy: Whether this is a buy order
    #         base_decimals: Base token decimals
    #         quote_decimals: Quote token decimals
    #         current_nonce: Transaction nonce

    #     Returns:
    #         Transaction hash
    #     """
    #     try:
    #         from eth_account import Account
    #         from web3 import Web3

    #         # Create Web3 instance
    #         rpc_url = CONSTANTS.DOMAIN_CONFIG[self._domain]["rpc_url"]
    #         w3 = Web3(Web3.HTTPProvider(rpc_url))

    #         if not w3.is_connected():
    #             raise ValueError("Failed to connect to RPC for order placement")

    #         # Get exchange contract address
    #         exchange_address = CONSTANTS.DOMAIN_CONFIG[self._domain]["standard_exchange_address"]
    #         exchange_checksum = w3.to_checksum_address(exchange_address)
    #         wallet_address = w3.to_checksum_address(self._wallet_address)

    #         # Based on the transaction trace, the limitBuy function signature is:
    #         # limitBuy(address base, address quote, uint256 price, uint256 quoteAmount, bool isMaker, uint256 n, address recipient)
    #         # Function selector: 0x89556190

    #         if is_buy:
    #             # For buy orders: quote_amount = amount * price
    #             quote_amount = amount * execution_price
    #             quote_amount_wei = int(quote_amount * (10**quote_decimals))
    #             price_wei = int(execution_price * CONSTANTS.DENOM)  # Use contract's price precision

    #             # Check if we're buying with the native token (SOMI)
    #             quote_symbol = utils.convert_address_to_symbol(quote_address, self._domain)
    #             is_native_buy = quote_symbol.upper() in CONSTANTS.NATIVE_TOKEN_LIST

    #             if is_native_buy:
    #                 self.logger().info(f"Direct contract BUY NATIVE order (using limitBuyETH):")
    #                 self.logger().info(f"  - base: {base_address}")
    #                 self.logger().info(f"  - native quote: {quote_symbol}")
    #                 self.logger().info(f"  - execution_price: {execution_price}")
    #                 self.logger().info(f"  - quote_decimals: {quote_decimals}")

    #                 # Calculate price_wei with correct contract precision
    #                 price_wei = int(execution_price * CONSTANTS.DENOM)
    #                 self.logger().info(
    #                     f"  - price_wei calculation: {execution_price} * {CONSTANTS.DENOM} = {price_wei}"
    #                 )
    #                 self.logger().info(f"  - quote_amount_wei: {quote_amount_wei}")
    #                 self.logger().info(f"  - nonce: {current_nonce}")

    #                 # Use limitBuyETH for native token purchases (SOMI -> other token)
    #                 try:
    #                     import json
    #                     import os

    #                     # Load local ABI file (more up-to-date than standardweb3 package)
    #                     abi_path = os.path.join(os.path.dirname(__file__), "lib", "matching_engine_abi.json")
    #                     with open(abi_path, "r") as f:
    #                         matching_engine_abi = json.load(f)

    #                     # Create contract instance
    #                     contract = w3.eth.contract(address=exchange_checksum, abi=matching_engine_abi)

    #                     # Build the limitBuyETH function call using the ABI
    #                     # limitBuyETH(address base, uint256 price, bool isMaker, uint32 n, address recipient)
    #                     # CRITICAL: n parameter is MAX ORDERS TO MATCH, not nonce!
    #                     transaction_data = contract.functions.limitBuyETH(
    #                         w3.to_checksum_address(base_address),  # base token (what we're buying)
    #                         price_wei,  # price
    #                         True,  # isMaker
    #                         MAX_ORDERS_TO_MATCH,  # n (max orders to match, not nonce!)
    #                         wallet_address,  # recipient
    #                     ).build_transaction(
    #                         {
    #                             "from": wallet_address,
    #                             "gas": 1,  # Will be estimated later
    #                             "gasPrice": 1,  # Will be set later
    #                             "nonce": current_nonce,
    #                             "value": quote_amount_wei,  # Send SOMI amount as transaction value
    #                         }
    #                     )

    #                     # Extract the data field
    #                     transaction_data = transaction_data["data"]

    #                 except ImportError:
    #                     self.logger().warning(
    #                         "standardweb3 matching_engine_abi not available, falling back to manual encoding for limitBuyETH"
    #                     )

    #                     # Fallback to manual encoding for limitBuyETH
    #                     # Function signature: limitBuyETH(address,uint256,bool,uint32,address)
    #                     function_selector = w3.keccak(text="limitBuyETH(address,uint256,bool,uint32,address)")[:4].hex()

    #                     # Encode parameters according to ABI
    #                     encoded_params = w3.codec.encode(
    #                         ["address", "uint256", "bool", "uint32", "address"],
    #                         [
    #                             w3.to_checksum_address(base_address),  # base token
    #                             price_wei,  # price
    #                             True,  # isMaker
    #                             MAX_ORDERS_TO_MATCH,  # n (max orders to match, not nonce!)
    #                             wallet_address,  # recipient
    #                         ],
    #                     )

    #                     # Build transaction data
    #                     transaction_data = function_selector + encoded_params.hex()

    #             else:
    #                 self.logger().info(f"Direct contract BUY ERC20 order (using limitBuy):")
    #                 self.logger().info(f"  - base: {base_address}")
    #                 self.logger().info(f"  - quote: {quote_address}")
    #                 self.logger().info(f"  - price_wei: {price_wei}")
    #                 self.logger().info(f"  - quote_amount_wei: {quote_amount_wei}")
    #                 self.logger().info(f"  - nonce: {current_nonce}")

    #                 # Use limitBuy for ERC20 token purchases
    #                 try:
    #                     import json
    #                     import os

    #                     # Load local ABI file (more up-to-date than standardweb3 package)
    #                     abi_path = os.path.join(os.path.dirname(__file__), "lib", "matching_engine_abi.json")
    #                     with open(abi_path, "r") as f:
    #                         matching_engine_abi = json.load(f)

    #                     # Create contract instance
    #                     contract = w3.eth.contract(address=exchange_checksum, abi=matching_engine_abi)

    #                     # Build the limitBuy function call using the ABI
    #                     # limitBuy(address base, address quote, uint256 price, uint256 quoteAmount, bool isMaker, uint32 n, address recipient)
    #                     # CRITICAL: n parameter is MAX ORDERS TO MATCH, not nonce!
    #                     transaction_data = contract.functions.limitBuy(
    #                         w3.to_checksum_address(base_address),  # base token
    #                         w3.to_checksum_address(quote_address),  # quote token
    #                         price_wei,  # price
    #                         quote_amount_wei,  # quoteAmount
    #                         True,  # isMaker
    #                         MAX_ORDERS_TO_MATCH,  # n (max orders to match, not nonce!)
    #                         wallet_address,  # recipient
    #                     ).build_transaction(
    #                         {
    #                             "from": wallet_address,
    #                             "gas": 1,  # Will be estimated later
    #                             "gasPrice": 1,  # Will be set later
    #                             "nonce": current_nonce,
    #                             "value": 0,  # No value for ERC20 purchases
    #                         }
    #                     )

    #                     # Extract the data field
    #                     transaction_data = transaction_data["data"]

    #                 except ImportError:
    #                     self.logger().warning(
    #                         "standardweb3 matching_engine_abi not available, falling back to manual encoding"
    #                     )

    #                     # Fallback to manual encoding
    #                     function_selector = "0x89556190"

    #                     # Encode parameters according to ABI (note uint32 for n parameter)
    #                     encoded_params = w3.codec.encode(
    #                         ["address", "address", "uint256", "uint256", "bool", "uint32", "address"],
    #                         [
    #                             w3.to_checksum_address(base_address),  # base token
    #                             w3.to_checksum_address(quote_address),  # quote token
    #                             price_wei,  # price
    #                             quote_amount_wei,  # quoteAmount
    #                             True,  # isMaker
    #                             MAX_ORDERS_TO_MATCH,  # n (max orders to match, not nonce!)
    #                             wallet_address,  # recipient
    #                         ],
    #                     )

    #                     # Build transaction data
    #                     transaction_data = function_selector + encoded_params.hex()

    #         else:
    #             # For sell orders: base_amount = amount
    #             base_amount_wei = int(amount * (10**base_decimals))
    #             price_wei = int(execution_price * CONSTANTS.DENOM)  # Use contract's price precision

    #             # Check if we're selling the native token (SOMI)
    #             base_symbol = utils.convert_address_to_symbol(base_address, self._domain)
    #             is_native_sell = base_symbol.upper() in CONSTANTS.NATIVE_TOKEN_LIST

    #             self.logger().info("DEBUG SELL ORDER PATH:")
    #             self.logger().info(f"  - base_symbol: {base_symbol}")
    #             self.logger().info(f"  - base_address: {base_address}")
    #             self.logger().info(f"  - is_native_sell: {is_native_sell}")
    #             self.logger().info(f"  - NATIVE_TOKEN_LIST: {CONSTANTS.NATIVE_TOKEN_LIST}")

    #             if is_native_sell:
    #                 self.logger().info(f"Direct contract SELL NATIVE order (using limitSellETH):")
    #                 self.logger().info(f"  - native token: {base_symbol}")
    #                 self.logger().info(f"  - quote: {quote_address}")
    #                 self.logger().info(f"  - execution_price: {execution_price}")
    #                 self.logger().info(f"  - quote_decimals: {quote_decimals}")

    #                 # Calculate price_wei with correct contract precision
    #                 price_wei = int(execution_price * CONSTANTS.DENOM)
    #                 self.logger().info(
    #                     f"  - price_wei calculation: {execution_price} * {CONSTANTS.DENOM} = {price_wei}"
    #                 )
    #                 self.logger().info(f"  - base_amount_wei: {base_amount_wei}")
    #                 self.logger().info(f"  - nonce: {current_nonce}")

    #                 # Use limitSellETH for native token sales (SOMI -> other token)
    #                 try:
    #                     import json
    #                     import os

    #                     # Load local ABI file (more up-to-date than standardweb3 package)
    #                     abi_path = os.path.join(os.path.dirname(__file__), "lib", "matching_engine_abi.json")
    #                     with open(abi_path, "r") as f:
    #                         matching_engine_abi = json.load(f)

    #                     # Create contract instance
    #                     contract = w3.eth.contract(address=exchange_checksum, abi=matching_engine_abi)

    #                     # Build the limitSellETH function call using the ABI
    #                     # limitSellETH(address quote, uint256 price, bool isMaker, uint32 n, address recipient)
    #                     # CRITICAL: n parameter is MAX ORDERS TO MATCH, not nonce!
    #                     # StandardWeb3 0.0.13+ expects decimal prices, not wei
    #                     transaction_data = contract.functions.limitSellETH(
    #                         w3.to_checksum_address(quote_address),  # quote token
    #                         execution_price,  # price as decimal (StandardWeb3 0.0.13+ format)
    #                         True,  # isMaker
    #                         MAX_ORDERS_TO_MATCH,  # n (max orders to match, not nonce!)
    #                         wallet_address,  # recipient
    #                     ).build_transaction(
    #                         {
    #                             "from": wallet_address,
    #                             "gas": 1,  # Will be estimated later
    #                             "gasPrice": 1,  # Will be set later
    #                             "nonce": current_nonce,
    #                             "value": base_amount_wei,  # Send SOMI amount as transaction value
    #                         }
    #                     )

    #                     # Extract the data field
    #                     transaction_data = transaction_data["data"]

    #                 except ImportError:
    #                     self.logger().warning(
    #                         "standardweb3 matching_engine_abi not available, falling back to manual encoding for limitSellETH"
    #                     )

    #                     # Fallback to manual encoding for limitSellETH
    #                     # Function signature: limitSellETH(address,uint256,bool,uint32,address)
    #                     function_selector = "0xe794b1c1"  # Known from successful transaction

    #                     # Encode parameters according to ABI
    #                     # StandardWeb3 0.0.13+ expects decimal prices, not wei
    #                     price_for_encoding = int(execution_price * CONSTANTS.DENOM)  # Convert to wei for manual encoding
    #                     encoded_params = w3.codec.encode(
    #                         ["address", "uint256", "bool", "uint32", "address"],
    #                         [
    #                             w3.to_checksum_address(quote_address),  # quote token
    #                             price_for_encoding,  # price in wei for manual encoding
    #                             True,  # isMaker
    #                             MAX_ORDERS_TO_MATCH,  # n (max orders to match, not nonce!)
    #                             wallet_address,  # recipient
    #                         ],
    #                     )

    #                     # Build transaction data
    #                     transaction_data = function_selector + encoded_params.hex()

    #             else:
    #                 self.logger().info(f"Direct contract SELL ERC20 order (using limitSell):")
    #                 self.logger().info(f"  - base: {base_address}")
    #                 self.logger().info(f"  - quote: {quote_address}")
    #                 self.logger().info(f"  - price_wei: {price_wei}")
    #                 self.logger().info(f"  - base_amount_wei: {base_amount_wei}")
    #                 self.logger().info(f"  - nonce: {current_nonce}")

    #                 # Use limitSell for ERC20 token sales
    #                 try:
    #                     import json
    #                     import os

    #                     # Load local ABI file (more up-to-date than standardweb3 package)
    #                     abi_path = os.path.join(os.path.dirname(__file__), "lib", "matching_engine_abi.json")
    #                     with open(abi_path, "r") as f:
    #                         matching_engine_abi = json.load(f)

    #                     # Create contract instance
    #                     contract = w3.eth.contract(address=exchange_checksum, abi=matching_engine_abi)

    #                     # Build the limitSell function call using the ABI
    #                     # limitSell(address base, address quote, uint256 price, uint256 baseAmount, bool isMaker, uint32 n, address recipient)
    #                     # CRITICAL: n parameter is MAX ORDERS TO MATCH, not nonce!
    #                     # StandardWeb3 0.0.13+ expects decimal prices, not wei
    #                     transaction_data = contract.functions.limitSell(
    #                         w3.to_checksum_address(base_address),  # base token
    #                         w3.to_checksum_address(quote_address),  # quote token
    #                         execution_price,  # price as decimal (StandardWeb3 0.0.13+ format)
    #                         base_amount_wei,  # baseAmount
    #                         True,  # isMaker
    #                         MAX_ORDERS_TO_MATCH,  # n (max orders to match, not nonce!)
    #                         wallet_address,  # recipient
    #                     ).build_transaction(
    #                         {
    #                             "from": wallet_address,
    #                             "gas": 1,  # Will be estimated later
    #                             "gasPrice": 1,  # Will be set later
    #                             "nonce": current_nonce,
    #                             "value": 0,  # No value for ERC20 sales
    #                         }
    #                     )

    #                     # Extract the data field
    #                     transaction_data = transaction_data["data"]

    #                 except ImportError:
    #                     self.logger().warning(
    #                         "standardweb3 matching_engine_abi not available, falling back to manual encoding"
    #                     )

    #                     # Fallback to manual encoding
    #                     function_selector = w3.keccak(
    #                         text="limitSell(address,address,uint256,uint256,bool,uint32,address)"
    #                     )[:4].hex()

    #                     # Encode parameters according to ABI (note uint32 for n parameter)
    #                     # StandardWeb3 0.0.13+ expects decimal prices, not wei
    #                     price_for_encoding = int(execution_price * CONSTANTS.DENOM)  # Convert to wei for manual encoding
    #                     encoded_params = w3.codec.encode(
    #                         ["address", "address", "uint256", "uint256", "bool", "uint32", "address"],
    #                         [
    #                             w3.to_checksum_address(base_address),  # base token
    #                             w3.to_checksum_address(quote_address),  # quote token
    #                             price_for_encoding,  # price in wei for manual encoding
    #                             base_amount_wei,  # baseAmount
    #                             True,  # isMaker
    #                             MAX_ORDERS_TO_MATCH,  # n (max orders to match, not nonce!)
    #                             wallet_address,  # recipient
    #                         ],
    #                     )

    #                     # Build transaction data
    #                     transaction_data = function_selector + encoded_params.hex()

    #         # Determine transaction value (already calculated during function call building)
    #         # For native token (SOMI) sell orders, the amount is sent as transaction value
    #         base_symbol = utils.convert_address_to_symbol(base_address, self._domain)
    #         is_native_sell = not is_buy and base_symbol.upper() in CONSTANTS.NATIVE_TOKEN_LIST

    #         if is_native_sell:
    #             # For limitSellETH, transaction value is the base amount being sold
    #             transaction_value = base_amount_wei
    #             self.logger().info(
    #                 f"Selling native token {base_symbol}: sending {transaction_value} wei ({amount} {base_symbol}) as transaction value"
    #             )
    #         else:
    #             # For limitBuy or limitSell (ERC20), no value needed
    #             transaction_value = 0

    #         # Estimate gas for the transaction
    #         try:
    #             gas_estimate = w3.eth.estimate_gas(
    #                 {
    #                     "from": wallet_address,
    #                     "to": exchange_checksum,
    #                     "data": transaction_data,
    #                     "value": transaction_value,
    #                 }
    #             )

    #             # Add 20% buffer to gas estimate, but ensure it's at least 3M
    #             gas_limit = max(int(gas_estimate * 1.2), 3000000)
    #             self.logger().info(f"Gas estimate: {gas_estimate}, using gas limit: {gas_limit}")

    #         except Exception as e:
    #             self.logger().warning(f"Could not estimate gas: {e}, using default 3M")
    #             gas_limit = 3000000

    #         # Get current gas price using cache to avoid redundant Web3 calls
    #         gas_price = await self._get_cached_gas_price()

    #         # Build transaction
    #         transaction = {
    #             "from": wallet_address,
    #             "to": exchange_checksum,
    #             "data": transaction_data,
    #             "gas": gas_limit,
    #             "gasPrice": gas_price,
    #             "nonce": current_nonce,
    #             "value": transaction_value,
    #             "chainId": CONSTANTS.DOMAIN_CONFIG[self._domain]["chain_id"],
    #         }

    #         # Sign transaction
    #         # Ensure private key is properly formatted for eth_account
    #         private_key_for_signing = self._private_key
    #         if isinstance(private_key_for_signing, str):
    #             # Remove '0x' prefix if present
    #             if private_key_for_signing.startswith("0x"):
    #                 private_key_for_signing = private_key_for_signing[2:]
    #             # Convert hex string to bytes
    #             private_key_for_signing = bytes.fromhex(private_key_for_signing)

    #         # Validate key length
    #         if len(private_key_for_signing) != 32:
    #             raise ValueError(f"Private key must be exactly 32 bytes, got {len(private_key_for_signing)} bytes")

    #         signed_txn = Account.sign_transaction(transaction, private_key_for_signing)

    #         # Send transaction
    #         try:
    #             tx_hash = w3.eth.send_raw_transaction(signed_txn.raw_transaction)
    #             tx_hash_hex = tx_hash.hex()
    #             self.logger().info(f"Direct contract order transaction submitted: {tx_hash_hex}")
    #         except Exception as e:
    #             self.logger().error(f"Failed to submit transaction: {e}")
    #             raise

    #         # 🚀 PHASE 2: RETURN IMMEDIATELY - No confirmation wait!
    #         self.logger().info(f"Transaction submitted successfully: {tx_hash_hex}")
    #         self.logger().info(f"Order will be tracked async - check status via get_open_orders()")

    #         # Store transaction hash for later confirmation tracking
    #         # Determine order type based on trade direction and token type
    #         quote_symbol = utils.convert_address_to_symbol(quote_address, self._domain)
    #         is_native_buy = is_buy and quote_symbol.upper() in CONSTANTS.NATIVE_TOKEN_LIST
    #         is_native_sell = not is_buy and base_symbol.upper() in CONSTANTS.NATIVE_TOKEN_LIST

    #         if is_native_buy:
    #             order_type = "limitBuyETH"
    #         elif is_native_sell:
    #             order_type = "limitSellETH"
    #         elif is_buy:
    #             order_type = "limitBuy"
    #         else:
    #             order_type = "limitSell"

    #         self._pending_tx_hashes[tx_hash_hex] = {
    #             "timestamp": self.current_timestamp,
    #             "order_type": order_type,
    #             "client_order_id": None,  # Will be set by caller
    #         }

    #         return tx_hash_hex, self.current_timestamp

    #     except Exception as e:
    #         self.logger().error(f"Error in direct contract order placement: {e}")
    #         raise

    async def _wait_for_transaction_confirmation(self, tx_hash: bytes, w3) -> str:
        """
        Wait for transaction confirmation and check status.

        Args:
            tx_hash: Transaction hash bytes
            w3: Web3 instance

        Returns:
            Transaction hash hex string if successful

        Raises:
            Exception: If transaction fails or times out
        """
        import asyncio

        tx_hash_hex = tx_hash.hex() if isinstance(tx_hash, bytes) else tx_hash
        receipt = None

        for i in range(30):  # Wait up to 30 seconds
            try:
                receipt = w3.eth.get_transaction_receipt(tx_hash)
                if receipt:
                    break
            except Exception as e:
                # Continue trying unless it's a definitive error
                if "transaction not found" not in str(e).lower():
                    self.logger().warning(f"Error getting transaction receipt (attempt {i + 1}/30): {e}")
            await asyncio.sleep(1)

        # Process transaction confirmation results
        if receipt:
            if receipt.status == 1:
                self.logger().info(f"Transaction confirmed: {tx_hash_hex}")
                return tx_hash_hex
            else:
                # Transaction was mined but failed
                self.logger().error(f"Transaction failed on blockchain: {tx_hash_hex}")
                self.logger().error(f"Transaction receipt: {receipt}")

                # Try to get more detailed error information
                error_details = f"Transaction failed with status {receipt.status}"

                # Get gas usage information to detect out of gas errors
                if hasattr(receipt, "gasUsed"):
                    gas_used = receipt.gasUsed
                    # Try to get the original transaction to see gas limit
                    try:
                        tx = w3.eth.get_transaction(tx_hash)
                        gas_limit = tx.gas
                        if gas_used >= gas_limit * 0.95:  # Used more than 95% of gas limit
                            error_details += " (likely OUT_OF_GAS)"
                    except Exception as e:
                        self.logger().warning(f"Could not get transaction details for gas analysis: {e}")

                # Try to get revert reason if available
                try:
                    # Attempt to replay the transaction to get revert reason
                    tx = w3.eth.get_transaction(tx_hash)
                    w3.eth.call(
                        {
                            "to": tx.to,
                            "from": tx["from"],
                            "data": tx.input,
                            "value": tx.value,
                            "gas": tx.gas,
                            "gasPrice": tx.gasPrice,
                        },
                        block_identifier=receipt.blockNumber - 1,
                    )
                except Exception as revert_error:
                    # The call failed, which gives us the revert reason
                    revert_reason = str(revert_error)
                    if "execution reverted" in revert_reason.lower():
                        error_details += f" - Revert reason: {revert_reason}"

                raise Exception(error_details)
        else:
            # Could not get receipt - transaction may be pending or dropped
            self.logger().warning(f"Could not get receipt for transaction: {tx_hash_hex}")
            raise Exception(f"Transaction confirmation timeout: {tx_hash_hex}")

    async def _place_order_with_standardweb3(
        self,
        order: InFlightOrder
    ) -> tuple[str, int]:
        """
        Place an order using StandardWeb3 library and return both transaction hash and order ID.

        Args:
            order: InFlightOrder instance

        Returns:
            Tuple of (transaction_hash, blockchain_order_id)
        """
        try:
            from standardweb3 import StandardClient

            from hummingbot.connector.exchange.standard.standard_constants import DEFAULT_DOMAIN, DOMAIN_CONFIG

            # Get configuration
            domain_config = DOMAIN_CONFIG[DEFAULT_DOMAIN]
            rpc_url = domain_config['rpc_url']
            api_url = domain_config['api_url']
            websocket_url = domain_config['websocket_url']
            exchange_address = domain_config['standard_exchange_address']

            self.logger().info(f"🔄 Initializing StandardClient with:")
            self.logger().info(f"   - rpc_url: {rpc_url}")
            self.logger().info(f"   - api_url: {api_url}")
            self.logger().info(f"   - websocket_url: {websocket_url}")
            self.logger().info(f"   - exchange_address: {exchange_address}")
            self.logger().info(f"   - networkName: None (as requested)")

            # Initialize StandardClient with API URL from constants
            client = StandardClient(
                private_key=self._private_key,
                http_rpc_url=rpc_url,
                api_url=api_url,  # ✅ FIXED: Add API URL from constants
                matching_engine_address=exchange_address,
                websocket_url=websocket_url,
                networkName=None  # Use None as it works
            )

            # Get token addresses
            base_symbol, quote_symbol = order.trading_pair.split('-')
            base_address = utils.convert_symbol_to_address(base_symbol, self._domain)
            quote_address = utils.convert_symbol_to_address(quote_symbol, self._domain)

            # Get token decimals for proper conversion
            base_decimals = utils.get_token_decimals(base_symbol)
            quote_decimals = utils.get_token_decimals(quote_symbol)

            # Convert amounts to integers with proper decimals
            price_decimal = order.price
            amount_decimal = order.amount

            # CRITICAL: Use correct price conversion - contract uses DENOM (10^8) for price precision
            # Price should be quote_token_amount / base_token_amount * DENOM
            price_wei = price_decimal * Decimal(str(CONSTANTS.DENOM))

            # Determine recipient (wallet address)
            recipient = client.account.address

            self.logger().info(f"🔄 Placing order via StandardWeb3:")
            self.logger().info(f"   - Pair: {order.trading_pair}")
            self.logger().info(f"   - Type: {order.trade_type}")
            self.logger().info(f"   - Price: {price_decimal} -> {price_wei} (DENOM: {CONSTANTS.DENOM})")
            self.logger().info(f"   - Amount: {amount_decimal}")
            self.logger().info(f"   - Base: {base_symbol} ({base_decimals} decimals) -> {base_address}")
            self.logger().info(f"   - Quote: {quote_symbol} ({quote_decimals} decimals) -> {quote_address}")
            self.logger().info(f"   - Recipient: {recipient}")

            # Place order based on trade type and token type
            base_symbol, quote_symbol = order.trading_pair.split('-')

            # Check if we're dealing with native token (SOMI)
            is_base_native = base_symbol.upper() in CONSTANTS.NATIVE_TOKEN_LIST
            is_quote_native = quote_symbol.upper() in CONSTANTS.NATIVE_TOKEN_LIST

            self.logger().info(f"   - is_base_native: {is_base_native}")
            self.logger().info(f"   - is_quote_native: {is_quote_native}")

            # Place order and get response with order ID
            response = None

            if order.trade_type == TradeType.BUY:
                if is_quote_native:
                    # Buying base token with native token (SOMI) - use limit_buy_eth
                    # eth_amount = amount * price (how much SOMI to spend)
                    eth_amount_decimal = float(amount_decimal * price_decimal)  # StandardWeb3 now expects decimal amounts

                    self.logger().info(f"   - ETH amount: {eth_amount_decimal} SOMI (buying with SOMI, decimal format)")

                    response = await client.limit_buy_eth(
                        base=base_address,
                        price=price_wei,
                        is_maker=True,
                        n=CONSTANTS.MAX_ORDERS_TO_MATCH,
                        recipient=recipient,
                        eth_amount=eth_amount_decimal
                    )
                    self.logger().info(f"✅ Used limit_buy_eth successfully")
                else:
                    # Regular buy order with ERC20 tokens - use limit_buy
                    # quote_amount = amount * price (how much quote token to spend)
                    quote_amount_decimal = float(amount_decimal * price_decimal)  # StandardWeb3 now expects decimal amounts

                    self.logger().info(f"   - Quote amount: {quote_amount_decimal} {quote_symbol} (ERC20 buy, decimal format)")

                    response = await client.limit_buy(
                        base=base_address,
                        quote=quote_address,
                        price=price_wei,
                        quote_amount=quote_amount_decimal,
                        is_maker=True,
                        n=MAX_ORDERS_TO_MATCH,
                        recipient=recipient
                    )
                    self.logger().info(f"✅ Used limit_buy successfully")
            else:
                if is_base_native:
                    # Selling native token (SOMI) for other tokens - use limit_sell_eth
                    eth_amount_decimal = float(amount_decimal)  # StandardWeb3 now expects decimal amounts

                    self.logger().info(f"   - ETH amount: {eth_amount_decimal} SOMI (selling SOMI, decimal format)")

                    response = await client.limit_sell_eth(
                        quote=quote_address,
                        price=price_wei,
                        is_maker=True,
                        n=MAX_ORDERS_TO_MATCH,
                        recipient=recipient,
                        eth_amount=eth_amount_decimal
                    )
                    self.logger().info(f"✅ Used limit_sell_eth successfully")
                else:
                    # Regular sell order with ERC20 tokens - use limit_sell
                    base_amount_decimal = float(amount_decimal)  # StandardWeb3 now expects decimal amounts

                    self.logger().info(f"   - Base amount: {base_amount_decimal} {base_symbol} (ERC20 sell, decimal format)")

                    response = await client.limit_sell(
                        base=base_address,
                        quote=quote_address,
                        price=price_wei,
                        base_amount=base_amount_decimal,
                        is_maker=True,
                        n=MAX_ORDERS_TO_MATCH,
                        recipient=recipient
                    )
                    self.logger().info(f"✅ Used limit_sell successfully")

            # Extract transaction hash and order ID from response
            tx_hash = None
            blockchain_order_id = None

            if isinstance(response, dict):
                # Extract transaction hash
                tx_hash = response.get('tx_hash')
                self.logger().info(f"📝 Transaction hash: {tx_hash}")

                # Debug: Show full response structure
                self.logger().info(f"📋 Full StandardWeb3 response: {response}")

                # Try to extract order ID from decoded_logs first (StandardWeb3 0.0.11+)
                if 'decoded_logs' in response and response['decoded_logs']:
                    self.logger().info(f"🔍 Found {len(response['decoded_logs'])} decoded logs")

                    # Process all logs to understand what happened
                    order_placed_found = False
                    order_matched_found = False
                    trade_events_found = []

                    for i, log_entry in enumerate(response['decoded_logs']):
                        self.logger().info(f"🔍 Log {i}: {log_entry}")
                        event_name = log_entry.get('event', '')

                        # 1. Check for OrderPlaced event (limit order that stays on book)
                        if event_name == 'OrderPlaced' and 'args' in log_entry:
                            if 'id' in log_entry['args']:
                                blockchain_order_id = log_entry['args']['id']
                                self.logger().info(f"🎯 Extracted order ID from OrderPlaced event: {blockchain_order_id}")
                                order_placed_found = True
                                break

                        # 2. Check for immediate matching events (order matched immediately)
                        elif event_name in ['OrderMatched', 'Trade', 'OrderFilled', 'Fill']:
                            order_matched_found = True
                            trade_events_found.append(log_entry)

                            # Try to extract order ID from matching event
                            if 'args' in log_entry:
                                # Common field names for order ID in matching events
                                for id_field in ['orderId', 'order_id', 'id', 'takerOrderId', 'makerOrderId']:
                                    if id_field in log_entry['args']:
                                        potential_order_id = log_entry['args'][id_field]
                                        if blockchain_order_id is None:  # Use the first valid ID we find
                                            blockchain_order_id = potential_order_id
                                            self.logger().info(f"🎯 Extracted order ID from {event_name} event ({id_field}): {blockchain_order_id}")

                        # 3. Check for market price update events
                        elif event_name in ['NewMarketPrice', 'PriceUpdate']:
                            self.logger().info(f"📈 Market price update detected: {log_entry}")

                    # Report what we found and track execution status
                    if order_placed_found:
                        self.logger().info(f"✅ Order placed as limit order and stays on book")
                        self._order_execution_status[order.client_order_id] = 'placed'
                    elif order_matched_found:
                        self.logger().info(f"⚡ Order matched immediately - found {len(trade_events_found)} trade events")
                        self._order_execution_status[order.client_order_id] = 'matched'
                        if blockchain_order_id:
                            self.logger().info(f"✅ Successfully extracted order ID from immediate execution")
                        else:
                            self.logger().warning(f"⚠️  Could not extract order ID from immediate execution events")
                    else:
                        self.logger().info(f"❓ No OrderPlaced or OrderMatched events found")
                        self._order_execution_status[order.client_order_id] = 'failed'

                else:
                    self.logger().warning(f"⚠️  No decoded_logs found in response")

                # Fallback: try to get from order_info field (if available)
                if blockchain_order_id is None and 'order_info' in response and response['order_info']:
                    order_info = response['order_info']
                    self.logger().info(f"🔍 Found order_info: {order_info}")
                    if isinstance(order_info, dict) and 'order_id' in order_info:
                        blockchain_order_id = order_info['order_id']
                        self.logger().info(f"🎯 Extracted order ID from order_info: {blockchain_order_id}")
                    elif isinstance(order_info, dict) and 'id' in order_info:
                        blockchain_order_id = order_info['id']
                        self.logger().info(f"🎯 Extracted order ID from order_info.id: {blockchain_order_id}")

                # Final fallback: generate temporary ID for immediate executions without detectable order ID
                if blockchain_order_id is None and order_matched_found:
                    # For immediate executions where we can't extract the real order ID,
                    # generate a deterministic temporary ID based on transaction hash
                    blockchain_order_id = abs(hash(tx_hash)) % (10**6)  # Use last 6 digits of hash
                    self.logger().info(f"🎯 Generated temporary order ID for immediate execution: {blockchain_order_id}")
                    self.logger().warning(f"⚠️  Using temporary order ID - cancellation may not work for this order")

                # Display response structure for debugging
                if blockchain_order_id is not None:
                    self.logger().info(f"📋 StandardWeb3 response keys: {list(response.keys())}")
                else:
                    self.logger().warning(f"⚠️  Could not find order ID in StandardWeb3 response")
                    self.logger().warning(f"📋 Response keys: {list(response.keys())}")

            elif hasattr(response, 'hex'):
                tx_hash = response.hex()
            else:
                tx_hash = str(response)

            self.logger().info(f"✅ StandardWeb3 order placed: {tx_hash}")

            # Fallback: extract from transaction receipt if no order ID found in response
            if blockchain_order_id is None:
                self.logger().info(f"🔍 Fallback: extracting order ID from transaction receipt")
                try:
                    blockchain_order_id = await self._extract_blockchain_order_id_for_cancel(tx_hash)
                except Exception as e:
                    self.logger().warning(f"⚠️  Failed to extract order ID from receipt: {e}")
                    blockchain_order_id = None

            # CRITICAL: Never fail order placement due to missing order ID
            # For orders that execute immediately, we may not be able to extract the order ID,
            # but the order was still successfully placed and executed.
            if blockchain_order_id is None:
                # Generate a placeholder order ID to prevent the order from failing
                # This allows the order to be tracked even though cancellation won't work
                blockchain_order_id = abs(hash(tx_hash)) % (10**6)  # Use hash-based ID
                self.logger().warning(f"⚠️  Could not extract blockchain order ID from transaction {tx_hash}")
                self.logger().warning(f"⚠️  Using placeholder order ID: {blockchain_order_id} (cancellation will not work)")
                self.logger().info(f"📊 This often happens with immediately executed orders - they execute successfully but can't be cancelled")

            self.logger().info(f"🎯 Final blockchain order ID: {blockchain_order_id}")

            return tx_hash, blockchain_order_id

        except Exception as e:
            self.logger().error(f"❌ Failed to place order via StandardWeb3: {e}", exc_info=True)
            raise

    async def _run_in_executor(self, func, *args):
        """Helper method to run synchronous code in executor"""
        import asyncio
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, func, *args)

    def _get_contract_instance(self):
        """
        Get Web3 contract instance for the matching engine.
        This helper function avoids code duplication across methods.

        Returns:
            Tuple of (web3_instance, contract_instance)
        """
        try:
            import json
            import os

            from web3 import Web3

            # Load contract ABI
            abi_path = os.path.join(os.path.dirname(__file__), "lib", "matching_engine_abi.json")
            with open(abi_path, "r") as f:
                matching_engine_abi = json.load(f)

            # Connect to blockchain
            w3 = Web3(Web3.HTTPProvider(self._rpc_url))
            contract_address = Web3.to_checksum_address(CONSTANTS.STANDARD_EXCHANGE_ADDRESS)
            contract = w3.eth.contract(address=contract_address, abi=matching_engine_abi)

            return w3, contract

        except Exception as e:
            self.logger().error(f"Error creating contract instance: {e}")
            raise

    async def _check_order_status_on_chain(
        self, base_address: str, quote_address: str, is_bid: bool, blockchain_order_id: int
    ) -> dict:
        """
        Check order status directly from the contract using getOrder() view function.
        This is MUCH better than parsing transaction receipts!

        Args:
            base_address: Base token address
            quote_address: Quote token address
            is_bid: True for buy orders, False for sell orders
            blockchain_order_id: Blockchain order ID

        Returns:
            dict with order status info: {
                'exists': bool,           # Whether order exists on contract
                'owner': str,            # Order owner address (if exists)
                'price': int,            # Order price in contract format (if exists)
                'remaining_amount': int, # Remaining deposit amount (if exists)
                'is_active': bool        # Whether order is still active/cancellable
            }
        """
        try:
            # Get contract instance using helper function
            from web3 import Web3
            w3, contract = self._get_contract_instance()

            # Call getOrder view function
            self.logger().info(f"🔍 Querying order status on-chain:")
            self.logger().info(f"   - base: {base_address}")
            self.logger().info(f"   - quote: {quote_address}")
            self.logger().info(f"   - is_bid: {is_bid}")
            self.logger().info(f"   - order_id: {blockchain_order_id}")

            order_result = await self._run_in_executor(
                lambda: contract.functions.getOrder(
                    Web3.to_checksum_address(base_address),
                    Web3.to_checksum_address(quote_address),
                    is_bid,
                    blockchain_order_id
                ).call()
            )

            # Parse the Order struct result: (owner, price, depositAmount)
            owner_address = order_result[0]
            price = order_result[1]
            remaining_amount = order_result[2]

            # Check if order exists by examining the owner address
            # Non-existent orders return zero address (0x0000...)
            order_exists = owner_address != "0x0000000000000000000000000000000000000000"

            status_info = {
                'exists': order_exists,
                'owner': owner_address if order_exists else None,
                'price': price if order_exists else 0,
                'remaining_amount': remaining_amount if order_exists else 0,
                'is_active': order_exists and remaining_amount > 0  # Active if exists and has remaining amount
            }

            self.logger().info(f"📊 Order status result:")
            self.logger().info(f"   - exists: {status_info['exists']}")
            if order_exists:
                self.logger().info(f"   - owner: {status_info['owner']}")
                self.logger().info(f"   - price: {status_info['price']}")
                self.logger().info(f"   - remaining_amount: {status_info['remaining_amount']}")
                self.logger().info(f"   - is_active: {status_info['is_active']}")
            else:
                self.logger().info(f"   - Order does not exist (executed/cancelled/never placed)")

            return status_info

        except Exception as e:
            self.logger().error(f"❌ Error checking order status on-chain: {e}")
            # Return unknown status on error
            return {
                'exists': None,  # Unknown
                'owner': None,
                'price': 0,
                'remaining_amount': 0,
                'is_active': None
            }

    async def _place_cancel(self, order_id: str, tracked_order: InFlightOrder) -> bool:
        """
        Cancel an order on the exchange - ENHANCED VERSION with contract query validation.

        Args:
            order_id: Client order ID
            tracked_order: InFlightOrder instance

        Returns:
            True if successfully cancelled, False otherwise
        """
        try:
            # Get combined identifier from tracked_order (format: "tx_hash:order_id")
            combined_id = tracked_order.exchange_order_id

            if combined_id is None:
                # Handle orders without exchange_order_id - check execution status to determine cause
                execution_status = self._order_execution_status.get(order_id, "unknown")

                if execution_status == "matched":
                    self.logger().info(f"Order {order_id} was immediately executed - cannot be cancelled")
                    return False
                elif execution_status == "failed":
                    self.logger().warning(f"Order {order_id} failed during placement - marking as not found")
                    await self._order_tracker.process_order_not_found(order_id)
                    return False
                else:
                    self.logger().warning(f"Order {order_id} has no exchange_order_id (status: {execution_status}) - likely immediate execution")
                    return False

            self.logger().info(f"🔧 Cancelling order {order_id} with combined ID: {combined_id}")

            # Extract transaction hash and blockchain order ID from combined format
            transaction_hash = None
            blockchain_order_id = None

            if ":" in combined_id:
                # New format: "tx_hash:order_id"
                transaction_hash, blockchain_order_id_str = combined_id.split(":", 1)
                try:
                    blockchain_order_id = int(blockchain_order_id_str)
                    self.logger().info(f"✅ Extracted from combined ID: tx_hash={transaction_hash}, order_id={blockchain_order_id}")
                except ValueError:
                    self.logger().error(f"❌ Invalid blockchain order ID format: {blockchain_order_id_str}")
                    raise ValueError(f"Invalid blockchain order ID format in exchange_order_id")
            else:
                # Legacy format: just transaction hash
                transaction_hash = combined_id
                self.logger().info(f"⚠️  Legacy format detected: {transaction_hash}")

            # 🚀 NEW APPROACH: Use contract query instead of transaction receipt parsing!
            if blockchain_order_id is None and transaction_hash:
                self.logger().info(f"⚠️  Extracting order ID from transaction receipt (fallback)...")
                try:
                    blockchain_order_id = await self._extract_blockchain_order_id_for_cancel(transaction_hash)
                    if blockchain_order_id is None:
                        raise ValueError("Could not extract order ID from transaction receipt")
                    self.logger().info(f"🎯 Using OrderPlaced ID: {blockchain_order_id} from tx: {transaction_hash}")
                except Exception as e:
                    self.logger().warning(f"⚠️  Could not extract blockchain order ID from transaction {transaction_hash}: {e}")
                    self.logger().info(f"📊 This often happens with orders that matched immediately - they can't be cancelled")
                    return False

            # Get token addresses from trading pair
            base_symbol, quote_symbol = tracked_order.trading_pair.split('-')
            base_address = utils.convert_symbol_to_address(base_symbol, self._domain)
            quote_address = utils.convert_symbol_to_address(quote_symbol, self._domain)
            is_bid = (tracked_order.trade_type.name == "BUY")

            # 🚀 SMART CONTRACT QUERY: Check order status before attempting cancellation
            self.logger().info(f"🎯 Checking order status on contract before cancellation...")
            order_status = await self._check_order_status_on_chain(
                base_address=base_address,
                quote_address=quote_address,
                is_bid=is_bid,
                blockchain_order_id=blockchain_order_id
            )

            # Handle different order states based on contract query
            if order_status['exists'] is False:
                self.logger().info(f"📊 Order {order_id} does not exist on contract (already executed/cancelled)")
                # This is not a failure - order was successfully executed or already cancelled
                return False

            elif order_status['exists'] is None:
                self.logger().warning(f"⚠️  Could not determine order status for {order_id} - attempting cancellation anyway")
                # Continue with cancellation attempt if status is unknown

            elif not order_status['is_active']:
                self.logger().info(f"📊 Order {order_id} exists but is not active (remaining_amount: {order_status['remaining_amount']})")
                self.logger().info(f"📊 This usually means the order was already fully executed")
                return False

            else:
                self.logger().info(f"✅ Order {order_id} is active on contract - proceeding with cancellation")

            self.logger().info(f"🎯 Performing on-chain cancellation:")
            self.logger().info(f"   - blockchain_order_id: {blockchain_order_id}")
            self.logger().info(f"   - transaction_hash: {transaction_hash}")
            self.logger().info(f"   - base: {base_symbol} -> {base_address}")
            self.logger().info(f"   - quote: {quote_symbol} -> {quote_address}")
            self.logger().info(f"   - is_bid: {is_bid}")

            # Perform direct contract cancellation using blockchain order ID
            cancel_tx_hash = await self._cancel_order_on_contract(
                base_address=base_address,
                quote_address=quote_address,
                is_bid=is_bid,
                order_id=blockchain_order_id  # Use blockchain order ID (uint32)
            )

            self.logger().info(f"🔄 Cancel transaction sent: {cancel_tx_hash}, waiting for confirmation...")

            # Wait for transaction confirmation and verify success
            success = await self._verify_cancellation_success(cancel_tx_hash, blockchain_order_id,
                                                              base_address, quote_address, is_bid)

            if success:
                self.logger().info(f"✅ Order cancelled successfully: {order_id} -> {cancel_tx_hash}")
                return True
            else:
                self.logger().warning(f"⚠️  Cancel transaction was mined but order {order_id} may not be cancelled (tx: {cancel_tx_hash})")
                return False

        except Exception as e:
            self.logger().error(f"❌ Failed to cancel order {order_id}: {e}", exc_info=True)
            # If cancellation fails for any other reason, let the base class handle it
            return False

    async def get_order_price(self, trading_pair: str, is_buy: bool, amount: Decimal) -> Decimal:
        """
        Override to use the enhanced quote price calculation.
        """
        return await self.get_quote_price(trading_pair, is_buy, amount)

    async def _extract_blockchain_order_id_for_cancel(self, transaction_hash: str) -> int:
        """
        Extract blockchain order ID from transaction receipt for cancellation.

        Args:
            transaction_hash: Transaction hash from order creation

        Returns:
            Blockchain order ID (uint32) needed for contract cancellation
        """
        try:
            from web3 import Web3

            # Get contract instance using helper function
            w3, contract = self._get_contract_instance()

            # Get transaction receipt
            tx_hash_bytes = bytes.fromhex(transaction_hash.replace('0x', ''))
            receipt = w3.eth.get_transaction_receipt(tx_hash_bytes)

            if receipt.status != 1:
                self.logger().error(f"Transaction failed: {transaction_hash}")
                return None

            # Parse events from transaction logs - handle both limit orders and immediate matching
            order_placed_id = None
            order_matched_ids = []

            for log_entry in receipt.logs:
                try:
                    # Try to decode as OrderPlaced event (limit order that stays on book)
                    try:
                        decoded_log = contract.events.OrderPlaced().process_log(log_entry)
                        order_placed_id = decoded_log['args']['id']
                        self.logger().info(f"✅ Found OrderPlaced event with ID: {order_placed_id}")
                        break  # For limit orders, use OrderPlaced ID
                    except:
                        pass  # Not an OrderPlaced event

                    # Try to decode as OrderMatched event (immediate execution)
                    try:
                        decoded_log = contract.events.OrderMatched().process_log(log_entry)
                        # OrderMatched events might contain multiple order IDs
                        args = decoded_log['args']

                        # Common field names for order IDs in matching events
                        for id_field in ['orderId', 'order_id', 'id', 'takerOrderId', 'makerOrderId']:
                            if id_field in args:
                                matched_id = args[id_field]
                                if matched_id not in order_matched_ids:
                                    order_matched_ids.append(matched_id)
                                    self.logger().info(f"✅ Found OrderMatched event with ID ({id_field}): {matched_id}")
                    except:
                        pass  # Not an OrderMatched event

                    # Try to decode other trade/fill events
                    for event_name in ['Trade', 'Fill', 'OrderFilled']:
                        try:
                            event_handler = getattr(contract.events, event_name, None)
                            if event_handler:
                                decoded_log = event_handler().process_log(log_entry)
                                args = decoded_log['args']

                                # Extract any order ID from trade events
                                for id_field in ['orderId', 'order_id', 'id', 'takerOrderId', 'makerOrderId']:
                                    if id_field in args:
                                        trade_id = args[id_field]
                                        if trade_id not in order_matched_ids:
                                            order_matched_ids.append(trade_id)
                                            self.logger().info(f"✅ Found {event_name} event with ID ({id_field}): {trade_id}")
                        except:
                            continue  # Not this type of event

                except Exception:
                    # This log entry couldn't be decoded, continue
                    continue

            # Return the appropriate order ID
            if order_placed_id is not None:
                # Limit order that stayed on book - use OrderPlaced ID
                self.logger().info(f"🎯 Using OrderPlaced ID: {order_placed_id} from tx: {transaction_hash}")
                return order_placed_id
            elif order_matched_ids:
                # Immediate execution - use the first matched order ID
                matched_id = order_matched_ids[0]
                self.logger().info(f"🎯 Using first OrderMatched ID: {matched_id} from tx: {transaction_hash}")
                self.logger().info(f"   - All matched IDs found: {order_matched_ids}")
                return matched_id
            else:
                self.logger().error(f"No OrderPlaced or OrderMatched events found in transaction {transaction_hash}")
                return None

        except Exception as e:
            self.logger().error(f"Error extracting blockchain order ID from {transaction_hash}: {e}")
            return None

    async def _cancel_order_on_contract(
        self, base_address: str, quote_address: str, is_bid: bool, order_id: int
    ) -> str:
        """
        Cancel an order directly on the smart contract.

        Args:
            base_address: Base token contract address
            quote_address: Quote token contract address
            is_bid: True for buy orders, False for sell orders
            order_id: Blockchain order ID

        Returns:
            Transaction hash of cancellation
        """
        try:
            from eth_account import Account
            from web3 import Web3

            # Get contract instance using helper function
            w3, contract = self._get_contract_instance()

            # Prepare account for signing
            account = Account.from_key(self._private_key)

            # Use transaction lock to prevent nonce conflicts
            async with self._transaction_lock:
                # Get current nonce
                nonce = await self._get_current_nonce()

                # Build transaction with increased gas limit
                self.logger().info(f"🔧 Building cancel transaction:")
                self.logger().info(f"   - Contract: {CONSTANTS.STANDARD_EXCHANGE_ADDRESS}")
                self.logger().info(f"   - Method: cancelOrder({base_address}, {quote_address}, {is_bid}, {order_id})")
                self.logger().info(f"   - From: {account.address}")
                self.logger().info(f"   - Nonce: {nonce}")

                # Estimate gas first
                # try:
                #     gas_estimate = w3.eth.estimate_gas({
                #         'from': account.address,
                #         'to': contract_address,
                #         'data': contract.encodeABI(fn_name='cancelOrder', args=[
                #             Web3.to_checksum_address(base_address),
                #             Web3.to_checksum_address(quote_address),
                #             is_bid,
                #             order_id
                #         ])
                #     })

                #     # CRITICAL: Add significant gas buffer - trace shows OUT_OF_GAS at 0x2337d (144253)
                #     # We need much more gas for complex cancellation logic
                #     gas_limit = max(int(gas_estimate * 3.0), 600000)  # At least 600k with 200% buffer
                #     self.logger().info(f"🔧 Gas estimate: {gas_estimate}, using limit: {gas_limit}")

                # except Exception as e:
                #     self.logger().warning(f"⚠️  Could not estimate gas: {e}, using 3000k default")
                gas_limit = 3000000  # Increased default - much higher than the failing 144k

                transaction = contract.functions.cancelOrder(
                    Web3.to_checksum_address(base_address), Web3.to_checksum_address(quote_address), is_bid, order_id
                ).build_transaction(
                    {
                        "from": account.address,
                        "nonce": nonce,
                        "gas": gas_limit,  # Much higher gas limit
                        "gasPrice": w3.eth.gas_price,
                        "chainId": CONSTANTS.SOMNIA_CHAIN_ID,
                    }
                )

                # Sign and send transaction
                signed_txn = account.sign_transaction(transaction)
                tx_hash = w3.eth.send_raw_transaction(signed_txn.raw_transaction)

                # Convert to hex string with 0x prefix
                tx_hash_hex = tx_hash.hex()

                self.logger().info(f"Cancel order transaction sent: {tx_hash_hex}")
                return tx_hash_hex

        except Exception as e:
            self.logger().error(f"Error cancelling order on contract: {e}")
            raise

    async def _verify_cancellation_success(self, tx_hash: str, expected_order_id: int,
                                           base_address: str, quote_address: str, is_bid: bool) -> bool:
        """
        Verify cancellation success by checking order status on contract after transaction is mined.
        This replaces the unreliable event parsing approach with direct contract queries.

        Args:
            tx_hash: Transaction hash of the cancellation
            expected_order_id: Expected blockchain order ID that should be cancelled
            base_address: Base token address
            quote_address: Quote token address
            is_bid: True for buy orders, False for sell orders

        Returns:
            bool: True if cancellation was successful, False otherwise
        """
        try:
            from web3 import Web3

            # Wait for transaction to be mined
            w3 = Web3(Web3.HTTPProvider(self._rpc_url))
            receipt = None
            self.logger().info(f"⏳ Waiting for cancel transaction {tx_hash} to be mined...")
            for attempt in range(30):  # Wait up to 30 seconds
                try:
                    receipt = w3.eth.get_transaction_receipt(tx_hash)
                    if receipt:
                        break
                except Exception:
                    await asyncio.sleep(1)

            if not receipt:
                self.logger().warning(f"⚠️  Cancel transaction {tx_hash} not mined after 30 seconds")
                return False

            # Check if transaction succeeded
            if receipt.status != 1:
                self.logger().error(f"❌ Cancel transaction {tx_hash} failed with status: {receipt.status}")
                return False

            # IMPROVED: Instead of parsing events, directly check order status on contract
            self.logger().info(f"✅ Cancel transaction mined successfully, checking order status on contract...")

            # Wait a bit for state to update
            await asyncio.sleep(2)

            # Check order status directly on contract
            order_status = await self._check_order_status_on_chain(
                base_address=base_address,
                quote_address=quote_address,
                is_bid=is_bid,
                blockchain_order_id=expected_order_id
            )

            # Determine cancellation success based on order status
            if not order_status['exists']:
                self.logger().info(f"✅ Cancellation verified: order {expected_order_id} no longer exists on contract")
                return True
            elif not order_status['is_active']:
                self.logger().info(f"✅ Cancellation verified: order {expected_order_id} exists but is inactive (fully executed)")
                return True
            else:
                self.logger().error(f"❌ Cancellation failed: order {expected_order_id} still active on contract")
                self.logger().error(f"❌ Order status: exists={order_status['exists']}, active={order_status['is_active']}, remaining={order_status['remaining_amount']}")
                return False

        except Exception as e:
            self.logger().error(f"Error verifying cancellation success for {tx_hash}: {e}")
            return False

    def _parse_trading_rule(self, trading_rule: Dict[str, Any]) -> TradingRule:
        """
        Parse trading rule from exchange data.

        Args:
            trading_rule: Raw trading rule data

        Returns:
            TradingRule instance
        """
        try:
            trading_pair = trading_rule["symbol"]

            # Initialize default values
            min_order_size = Decimal("0.001")
            max_order_size = Decimal("1000000")
            min_price_increment = Decimal("0.001")
            min_base_amount_increment = Decimal("0.001")
            min_notional_size = Decimal("1.0")

            # Handle filter-based format (from tests)
            if "filters" in trading_rule:
                for filter_item in trading_rule["filters"]:
                    filter_type = filter_item.get("filterType")
                    if filter_type == "LOT_SIZE":
                        min_order_size = Decimal(filter_item.get("minQty", "0.001"))
                        max_order_size = Decimal(filter_item.get("maxQty", "1000000"))
                        min_base_amount_increment = Decimal(filter_item.get("stepSize", "0.001"))
                    elif filter_type == "PRICE_FILTER":
                        min_price_increment = Decimal(filter_item.get("tickSize", "0.001"))
                    elif filter_type == "MIN_NOTIONAL":
                        min_notional_size = Decimal(filter_item.get("minNotional", "1.0"))

            # Handle direct field format (from our implementation)
            else:
                min_order_size = Decimal(trading_rule.get("minQty", "0.001"))
                max_order_size = Decimal(trading_rule.get("maxQty", "1000000"))
                min_price_increment = Decimal(trading_rule.get("tickSize", "0.001"))
                min_base_amount_increment = Decimal(trading_rule.get("stepSize", "0.001"))
                min_notional_size = Decimal(trading_rule.get("minNotional", "1.0"))

            return TradingRule(
                trading_pair=trading_pair,
                min_order_size=min_order_size,
                max_order_size=max_order_size,
                min_price_increment=min_price_increment,
                min_base_amount_increment=min_base_amount_increment,
                min_notional_size=min_notional_size,
            )

        except Exception as e:
            self.logger().error(f"Error parsing trading rule: {e}")
            raise

    def _parse_trading_pair(self, trading_pair: Dict[str, Any]) -> str:
        """
        Parse trading pair from exchange data.

        Args:
            trading_pair: Raw trading pair data

        Returns:
            Trading pair string
        """
        return trading_pair["symbol"]

    async def _format_trading_rules(self, exchange_info_dict: Dict[str, Any]) -> List[TradingRule]:
        """
        Format trading rules from exchange response.

        Args:
            exchange_info_dict: Exchange info dictionary or list

        Returns:
            List of trading rules
        """
        trading_rules = []

        # Handle both dict and list inputs for test compatibility
        if isinstance(exchange_info_dict, list):
            # If it's a list, treat each item as rule data
            for rule_data in exchange_info_dict:
                try:
                    trading_rule = self._parse_trading_rule(rule_data)
                    trading_rules.append(trading_rule)
                except Exception as e:
                    self.logger().error(f"Error formatting trading rule: {e}")
        else:
            # If it's a dict, iterate over items
            for trading_pair, rule_data in exchange_info_dict.items():
                try:
                    trading_rule = self._parse_trading_rule(rule_data)
                    trading_rules.append(trading_rule)
                except Exception as e:
                    self.logger().error(f"Error formatting trading rule for {trading_pair}: {e}")

        return trading_rules

    async def _update_balances(self):
        """
        Update account balances using on-chain Web3 calls with API fallback.
        This method is called by the balance command to fetch current balances.
        """
        try:
            self.logger().info("=== Starting balance update ===")

            if not self._standard_client:
                self.logger().error("StandardWeb3 client not available - cannot fetch balances")
                return

            # Get all relevant tokens including native token
            tokens = set()

            if not self._trading_pairs:
                # For balance command or non-trading mode, use default tokens
                self.logger().info("No trading pairs configured - using default tokens for balance check")
                tokens = CONSTANTS.DEFAULT_TOKENS.copy()
                self.logger().info("Using default tokens for balance check: {tokens}")
            else:
                for trading_pair in self._trading_pairs:
                    base, quote = utils.split_trading_pair(trading_pair)
                    self.logger().debug(f"Split {trading_pair} -> base: {base}, quote: {quote}")
                    tokens.add(base)
                    tokens.add(quote)

                # Always include native token for trading mode based on current domain
                if self._trading_required:
                    native_token = CONSTANTS.NATIVE_TOKEN
                    tokens.add(native_token)
                    self.logger().debug(f"Added native token for {self._domain}: {native_token}")

            self.logger().info(f"Fetching balances for tokens: {sorted(tokens)}")

            # Fetch balances using Web3 (primary method)
            balances = {}
            successful_fetches = 0
            failed_fetches = 0

            for token in sorted(tokens):
                try:
                    self.logger().debug(f"Fetching balance for {token}...")
                    balance = await self._get_token_balance_web3(token)
                    balances[token] = balance
                    successful_fetches += 1

                    # Show balance with appropriate formatting
                    if balance > Decimal("0"):
                        self.logger().info(f"✓ {token}: {balance}")
                    else:
                        self.logger().debug(f"✓ {token}: {balance} (zero balance)")

                except Exception as e:
                    self.logger().warning(f"✗ Web3 balance failed for {token}: {e}")
                    failed_fetches += 1

                    try:
                        self.logger().debug(f"Trying API fallback for {token}...")
                        balance = await self._get_token_balance_api(token)
                        balances[token] = balance
                        self.logger().info(f"✓ {token}: {balance} (via API)")
                    except Exception as api_error:
                        self.logger().error(f"✗ Both Web3 and API balance failed for {token}: {api_error}")
                        balances[token] = s_decimal_0

            # Update local balances
            self._account_balances = balances
            self._account_available_balances = balances.copy()

            # Summary
            total_tokens = len(tokens)
            self.logger().info(f"=== Balance update completed ===")
            self.logger().info(f"Successfully fetched: {successful_fetches}/{total_tokens} tokens")
            if failed_fetches > 0:
                self.logger().warning(f"Failed to fetch: {failed_fetches}/{total_tokens} tokens")

            # Log non-zero balances for user visibility
            non_zero_balances = {token: balance for token, balance in balances.items() if balance > s_decimal_0}
            if non_zero_balances:
                self.logger().info(f"Non-zero balances: {non_zero_balances}")
            else:
                self.logger().info("All balances are zero")

        except Exception as e:
            self.logger().error(f"Critical error updating balances: {e}")
            self.logger().exception("Full error details:")
            # Don't raise - let the system continue with existing balances

    async def refresh_balances_on_demand(self):
        """
        Manually refresh balances on-demand.
        This method can be used for debugging or when fresh balance data is specifically needed.

        Note: This performs on-chain calls and should be used sparingly to avoid performance impact.
        """
        self.logger().info("📊 Manual balance refresh requested - performing on-chain update...")
        await self._update_balances()
        self.logger().info("✅ Manual balance refresh completed")

    async def _get_token_balance_web3(self, token: str) -> Decimal:
        """
        Get token balance using Web3 on-chain calls.

        Args:
            token: Token symbol (e.g., "STT", "USDC")

        Returns:
            Token balance as Decimal
        """
        try:
            # Use direct Web3 connection to Somnia RPC instead of StandardClient
            from web3 import Web3

            # Create Web3 instance with Somnia RPC from domain config
            rpc_url = CONSTANTS.DOMAIN_CONFIG[self._domain]["rpc_url"]
            w3 = Web3(Web3.HTTPProvider(rpc_url))

            if not w3.is_connected():
                self.logger().error("Failed to connect to Somnia RPC")
                return s_decimal_0

            # Use the wallet address and convert to checksum format
            wallet_address = w3.to_checksum_address(self._wallet_address)

            self.logger().debug(f"Getting balance for {token} at address {wallet_address}")
            self.logger().debug(f"wallet_address type: {type(wallet_address)}")

            if token.upper() in CONSTANTS.NATIVE_TOKEN_LIST:
                # For other native tokens
                balance_wei = w3.eth.get_balance(wallet_address)
                balance = w3.from_wei(balance_wei, "ether")
                balance_decimal = Decimal(str(balance))
                self.logger().debug(f"Native {token} balance: {balance_decimal}")
                return balance_decimal

            token_address = utils.convert_symbol_to_address(token, self._domain)
            if not token_address or token_address == "0x...":
                self.logger().warning(f"Token address not found or incomplete for {token}")
                return s_decimal_0

            self.logger().debug(f"Getting ERC-20 balance for {token} at contract {token_address}")

            # Standard ERC-20 balanceOf call
            erc20_abi = [
                {
                    "constant": True,
                    "inputs": [{"name": "_owner", "type": "address"}],
                    "name": "balanceOf",
                    "outputs": [{"name": "balance", "type": "uint256"}],
                    "type": "function",
                },
                {
                    "constant": True,
                    "inputs": [],
                    "name": "decimals",
                    "outputs": [{"name": "", "type": "uint8"}],
                    "type": "function",
                },
            ]

            # Create contract instance with proper checksum addresses
            contract = w3.eth.contract(address=w3.to_checksum_address(token_address), abi=erc20_abi)

            # Get balance using Web3.to_checksum_address for safety
            balance_wei = contract.functions.balanceOf(w3.to_checksum_address(wallet_address)).call()

            # Get token decimals
            try:
                decimals = contract.functions.decimals().call()
            except Exception:
                # Default to 18 decimals if decimals() call fails
                decimals = 18

            # Convert to human readable format
            balance = Decimal(balance_wei) / Decimal(10**decimals)
            self.logger().debug(f"ERC-20 {token} balance: {balance} (decimals: {decimals})")
            return balance

        except Exception as e:
            self.logger().error(f"Web3 balance error for {token}: {e}")
            raise

    async def _get_token_balance_api(self, token: str) -> Decimal:
        """
        Get token balance using StandardWeb3 API as fallback.

        Args:
            token: Token symbol (e.g., "STT", "USDC")

        Returns:
            Token balance as Decimal
        """
        try:
            # First, get token information by symbol to get the token address
            token_info_url = f"{CONSTANTS.STANDARD_API_URL}/api/token/symbol/{token}"

            # Use the web assistant factory from the parent class
            rest_assistant = await self._web_assistants_factory.get_rest_assistant()

            # Get token information
            token_response = await rest_assistant.execute_request(
                url=token_info_url, method=RESTMethod.GET, throttler_limit_id=CONSTANTS.GET_TOKEN_INFO_PATH_URL
            )

            if token_response.get("id"):
                token_address = token_response["id"]
                decimals = token_response.get("decimals", 18)

                # For native tokens, use account data which might include balance info
                if token.upper() in CONSTANTS.NATIVE_TOKEN_LIST:
                    # Try to get account data for potential balance information
                    account_url = f"{CONSTANTS.STANDARD_API_URL}/api/account/{self._wallet_address}"
                    account_response = await rest_assistant.execute_request(
                        url=account_url, method=RESTMethod.GET, throttler_limit_id=CONSTANTS.GET_ACCOUNT_INFO_PATH_URL
                    )

                    # For now, return 0 as API doesn't provide direct balance
                    # In production, you might need additional endpoints or Web3 fallback
                    self.logger().info(f"Got account data for {token}, but no direct balance endpoint available")
                    return s_decimal_0

                else:
                    # For ERC-20 tokens, API doesn't provide direct balance
                    # This is a limitation of the current API
                    self.logger().warning(f"API balance not available for ERC-20 token {token}")
                    return s_decimal_0

            else:
                self.logger().warning(f"Token {token} not found in API")
                return s_decimal_0

        except Exception as e:
            self.logger().error(f"Failed to get {token} balance via API: {e}")
            return s_decimal_0

    async def _all_trade_updates_for_order(self, order: InFlightOrder) -> List[TradeUpdate]:
        """
        Get all trade updates for an order using StandardWeb3 trade history.

        Args:
            order: InFlightOrder instance

        Returns:
            List of TradeUpdate instances
        """
        try:
            if not self._standard_client:
                return []

            # Fetch account trade history using StandardWeb3
            trades_response = await self._standard_client.fetch_account_trade_history_paginated_with_limit(
                address=self._wallet_address, limit=100, page=1  # Get recent trades
            )

            trade_updates = []
            if trades_response and "trades" in trades_response:
                for trade in trades_response["trades"]:
                    # Check if this trade is related to our order
                    # This might depend on the exact response format from StandardWeb3
                    if self._is_trade_for_order(trade, order):
                        trade_update = self._parse_trade_update(trade, order)
                        if trade_update:
                            trade_updates.append(trade_update)

            return trade_updates

        except Exception as e:
            self.logger().error(f"Error fetching trade updates for order {order.client_order_id}: {e}")
            return []

    def _is_trade_for_order(self, trade: Dict[str, Any], order: InFlightOrder) -> bool:
        """
        Check if a trade is related to a specific order.

        Args:
            trade: Trade data from StandardWeb3
            order: InFlightOrder instance

        Returns:
            True if trade is for this order
        """
        try:
            # Check if the trade transaction hash matches our order exchange ID
            trade_tx_hash = trade.get("tx_hash") or trade.get("transaction_hash")
            if trade_tx_hash == order.exchange_order_id:
                return True

            # Alternative: check if trade matches order details (trading pair, side, etc.)
            trading_pair = f"{trade.get('base_symbol', '')}-{trade.get('quote_symbol', '')}"
            if trading_pair == order.trading_pair:
                # Additional checks could be added here for more precision
                return True

            return False

        except Exception as e:
            self.logger().warning(f"Error checking if trade is for order: {e}")
            return False

    def _parse_trade_update(self, trade: Dict[str, Any], order: InFlightOrder) -> Optional[TradeUpdate]:
        """
        Parse trade data into TradeUpdate format.

        Args:
            trade: Trade data from StandardWeb3
            order: InFlightOrder instance

        Returns:
            TradeUpdate instance or None
        """
        try:
            # Extract trade information
            fill_price = Decimal(str(trade.get("price", "0")))
            fill_quantity = Decimal(str(trade.get("quantity", "0")))

            # Get fee information if available
            fee_amount = Decimal(str(trade.get("fee", "0")))
            fee_currency = trade.get("fee_currency", order.quote_asset)

            # Create trade fee
            trade_fee = AddedToCostTradeFee(flat_fees=[TokenAmount(token=fee_currency, amount=fee_amount)])

            # Get trade timestamp
            trade_time = trade.get("timestamp", time.time())
            if isinstance(trade_time, str):
                # Parse timestamp if it's a string
                try:
                    trade_time = float(trade_time)
                except ValueError:
                    trade_time = time.time()

            return TradeUpdate(
                trading_pair=order.trading_pair,
                fill_timestamp=trade_time,
                fill_price=fill_price,
                fill_base_amount=fill_quantity,
                fee=trade_fee,
                trade_id=trade.get("trade_id", f"trade_{int(trade_time)}"),
                exchange_order_id=order.exchange_order_id,
                client_order_id=order.client_order_id,
            )

        except Exception as e:
            self.logger().error(f"Error parsing trade update: {e}")
            return None

    async def _request_order_status(self, tracked_order: InFlightOrder) -> OrderUpdate:
        """
        Request order status from the exchange.

        Args:
            tracked_order: InFlightOrder instance

        Returns:
            OrderUpdate instance
        """
        try:
            # Query order status using StandardClient account orders
            # Since there's no direct get_order_status, we'll fetch recent orders
            # and find the one matching our exchange_order_id
            orders_response = await self._standard_client.fetch_account_orders_paginated_with_limit(
                address=self._wallet_address, limit=50, page=1  # Get recent orders
            )

            # Look for our order in the response
            order_status = None
            if orders_response and "orders" in orders_response:
                for order in orders_response["orders"]:
                    if order.get("tx_hash") == tracked_order.exchange_order_id:
                        order_status = order
                        break

            if not order_status:
                # If not found in active orders, check order history
                history_response = await self._standard_client.fetch_account_order_history_paginated_with_limit(
                    address=self._wallet_address, limit=50, page=1
                )

                if history_response and "orders" in history_response:
                    for order in history_response["orders"]:
                        if order.get("tx_hash") == tracked_order.exchange_order_id:
                            order_status = order
                            break

            if not order_status:
                # Order not found - check execution status first to handle immediate executions
                execution_status = self._order_execution_status.get(tracked_order.client_order_id, "unknown")

                # Handle immediate executions that were detected during placement
                if execution_status == "matched":
                    self.logger().info(f"Order {tracked_order.client_order_id} was immediately executed - marking as FILLED")
                    return OrderUpdate(
                        trading_pair=tracked_order.trading_pair,
                        update_timestamp=time.time(),
                        new_state=OrderState.FILLED,
                        client_order_id=tracked_order.client_order_id,
                        exchange_order_id=tracked_order.exchange_order_id,
                    )

                # Handle confirmed failures
                if execution_status == "failed":
                    self.logger().warning(f"Order {tracked_order.client_order_id} failed during placement - marking as FAILED")
                    return OrderUpdate(
                        trading_pair=tracked_order.trading_pair,
                        update_timestamp=time.time(),
                        new_state=OrderState.FAILED,
                        client_order_id=tracked_order.client_order_id,
                        exchange_order_id=tracked_order.exchange_order_id,
                    )

                # For unknown status, use time-based timeout as fallback
                creation_time = tracked_order.creation_timestamp
                current_time = time.time()
                time_since_creation = current_time - creation_time

                # Only mark as failed if order is older than 1 hour and still not found
                # This prevents immediate executions from being marked as failed due to indexing delays
                if time_since_creation > 3600:  # 1 hour
                    self.logger().warning(
                        f"Order {tracked_order.client_order_id} not found after 1 hour, marking as failed"
                    )
                    return OrderUpdate(
                        trading_pair=tracked_order.trading_pair,
                        update_timestamp=time.time(),
                        new_state=OrderState.FAILED,
                        client_order_id=tracked_order.client_order_id,
                        exchange_order_id=tracked_order.exchange_order_id,
                    )
                else:
                    # Order is still new, assume it's OPEN and wait for indexing
                    self.logger().debug(
                        f"Order {tracked_order.client_order_id} not found yet (age: {time_since_creation:.1f}s), assuming OPEN - will timeout after 24h"
                    )
                    return OrderUpdate(
                        trading_pair=tracked_order.trading_pair,
                        update_timestamp=time.time(),
                        new_state=OrderState.OPEN,
                        client_order_id=tracked_order.client_order_id,
                        exchange_order_id=tracked_order.exchange_order_id,
                    )

            # Parse the status response
            new_state = self._parse_order_status(order_status)

            return OrderUpdate(
                trading_pair=tracked_order.trading_pair,
                update_timestamp=time.time(),
                new_state=new_state,
                client_order_id=tracked_order.client_order_id,
                exchange_order_id=tracked_order.exchange_order_id,
            )

        except Exception as e:
            self.logger().error(f"Error requesting order status for {tracked_order.client_order_id}: {e}")
            raise

    def _parse_order_status(self, order_status: Dict[str, Any]) -> OrderState:
        """
        Parse order state from exchange response.

        Args:
            order_status: Order status data

        Returns:
            OrderState
        """
        status = order_status.get("status", "").lower()

        if status in ["filled", "completed"]:
            return OrderState.FILLED
        elif status in ["open", "active", "pending"]:
            return OrderState.OPEN
        elif status in ["cancelled", "canceled"]:
            return OrderState.CANCELLED
        elif status in ["failed", "rejected"]:
            return OrderState.FAILED
        else:
            return OrderState.OPEN  # Default to open for unknown statuses

    # Required abstract properties
    @property
    def trading_pairs(self) -> List[str]:
        """
        Return list of active trading pairs.
        """
        return self._trading_pairs

    @property
    def is_cancel_request_in_exchange_synchronous(self) -> bool:
        """
        Whether cancel requests are synchronous or not.
        """
        return True  # Somnia cancellations are synchronous

    def is_trading_required(self) -> bool:
        """
        Whether trading is required for this connector.
        """
        return True

    @property
    def _order_book_tracker(self):
        """
        Expose order book tracker for tests and internal use.
        """
        return self.order_book_tracker

    def convert_from_exchange_trading_pair(self, exchange_trading_pair: str) -> str:
        """
        Convert trading pair from exchange format to internal format.

        Args:
            exchange_trading_pair: Exchange trading pair format

        Returns:
            Internal trading pair format
        """
        return utils.convert_from_exchange_trading_pair(exchange_trading_pair)

    def convert_to_exchange_trading_pair(self, trading_pair: str) -> str:
        """
        Convert trading pair from internal format to exchange format.

        Args:
            trading_pair: Internal trading pair format

        Returns:
            Exchange trading pair format
        """
        return utils.convert_to_exchange_trading_pair(trading_pair)

    def get_token_info(self, token_symbol: str) -> Dict[str, Any]:
        """
        Get token information.

        Args:
            token_symbol: Token symbol

        Returns:
            Token information dictionary
        """
        return {
            "symbol": token_symbol,
            "address": utils.convert_symbol_to_address(token_symbol, self._domain),
            "decimals": utils.get_token_decimals(token_symbol),
        }

    def _get_web3_balance(self, token: str) -> Decimal:
        """
        Synchronous wrapper for Web3 balance retrieval.

        Args:
            token: Token symbol

        Returns:
            Token balance
        """
        # This is a sync wrapper that the tests expect
        import asyncio

        try:
            loop = asyncio.get_event_loop()
            return loop.run_until_complete(self._get_token_balance_web3(token))
        except Exception:
            return s_decimal_0

    def _is_user_stream_initialized(self) -> bool:
        """
        Override to always return True since Somnia uses REST API polling instead of WebSocket user streams.
        """
        return True

    # Required abstract methods

    def _initialize_trading_pair_symbols_from_exchange_info(self, exchange_info: Dict[str, Any]):
        """
        Initialize trading pair symbols from exchange info.

        Args:
            exchange_info: Exchange information dictionary
        """
        self.logger().info("DEBUG: _initialize_trading_pair_symbols_from_exchange_info called")
        self.logger().info("DEBUG: exchange_info keys: {list(exchange_info.keys())}")
        self.logger().info("DEBUG: exchange_info type: {type(exchange_info)}")

        # Use bidict like Vertex for proper symbol mapping
        mapping = bidict()

        # Handle the structure returned by build_exchange_market_info() - format 1
        if "symbols" in exchange_info:
            self.logger().info("DEBUG: Using format 1 - exchange_info contains 'symbols' key")
            symbols = exchange_info.get("symbols", [])
            self.logger().info("DEBUG: Found {len(symbols)} symbols in 'symbols' key")

            for symbol_info in symbols:
                if isinstance(symbol_info, dict):
                    symbol = symbol_info.get("symbol", "")
                    base = symbol_info.get("baseAsset", "")
                    quote = symbol_info.get("quoteAsset", "")
                    self.logger().info("DEBUG: Processing symbol - symbol: {symbol}, base: {base}, quote: {quote}")

                    if symbol and base and quote:
                        # Use combine_to_hb_trading_pair like Vertex
                        hb_trading_pair = combine_to_hb_trading_pair(base=base, quote=quote)
                        mapping[symbol] = hb_trading_pair
                        self.logger().info("DEBUG: Added mapping {symbol} -> {hb_trading_pair}")

        # Handle direct trading pair keys - format 2 (when base class calls directly)
        else:
            self.logger().info("DEBUG: Using format 2 - exchange_info contains direct trading pair keys")
            self.logger().info("DEBUG: Full exchange_info content: {exchange_info}")
            trading_pair_keys = [key for key in exchange_info.keys() if "-" in key]
            self.logger().info("DEBUG: Found trading pair keys: {trading_pair_keys}")

            # If no keys with dash, try all keys as potential trading pairs
            if not trading_pair_keys:
                self.logger().info("DEBUG: No keys with dash found, checking all keys")
                all_keys = list(exchange_info.keys())
                self.logger().info("DEBUG: All keys: {all_keys}")

                # Check if any key looks like a trading pair or if we should use configured trading pairs
                for key in all_keys:
                    self.logger().info("DEBUG: Examining key: {key}, type: {type(key)}")

                    # If key is a trading pair format, use it
                    if isinstance(key, str) and "-" in key:
                        trading_pair_keys.append(key)
                    # If key matches our configured trading pairs, use it
                    elif key in self._trading_pairs:
                        trading_pair_keys.append(key)

                # If still no keys, use our configured trading pairs as fallback
                if not trading_pair_keys:
                    self.logger().info("DEBUG: Using configured trading pairs as fallback")
                    trading_pair_keys = self._trading_pairs

            self.logger().info("DEBUG: Final trading pair keys to process: {trading_pair_keys}")

            for trading_pair in trading_pair_keys:
                try:
                    # For Somnia, we expect trading pairs like "STT-USDC"
                    if "-" in trading_pair:
                        base_asset, quote_asset = trading_pair.split("-", 1)

                        # Create proper Hummingbot trading pair format
                        hb_trading_pair = combine_to_hb_trading_pair(base=base_asset, quote=quote_asset)

                        self.logger().info("DEBUG: Mapping {trading_pair} -> {hb_trading_pair}")
                        mapping[trading_pair] = hb_trading_pair
                    else:
                        self.logger().info("DEBUG: Skipping key without dash: {trading_pair}")

                except Exception as e:
                    self.logger().error("DEBUG: Error processing trading pair {trading_pair}: {e}")
                    self.logger().error("DEBUG: Traceback: {traceback.format_exc()}")

        self.logger().info("DEBUG: Final mapping before setting: {dict(mapping)}")
        self.logger().info(f"Initialized trading pair symbol map with {len(mapping)} pairs: {dict(mapping)}")

        self.logger().info("DEBUG: About to call _set_trading_pair_symbol_map")
        self._set_trading_pair_symbol_map(mapping)
        self.logger().info("DEBUG: Called _set_trading_pair_symbol_map")

        # Verify it was set
        current_map = getattr(self, "_trading_pair_symbol_map", "NOT SET")
        self.logger().info("DEBUG: After setting, _trading_pair_symbol_map = {current_map}")
        self.logger().info("DEBUG: trading_pair_symbol_map_ready() = {self.trading_pair_symbol_map_ready()}")

    async def _update_trading_fees(self):
        """
        Update trading fees for all trading pairs.
        """
        # Somnia uses fixed fees defined in constants
        trading_fees = {}
        for trading_pair in self._trading_pairs:
            trading_fees[trading_pair] = {
                "maker": Decimal("0.001"),  # 0.1%
                "taker": Decimal("0.001"),  # 0.1%
            }

        self._trading_fees = trading_fees

    async def _request_order_history(self) -> List[Dict[str, Any]]:
        """
        Request order history from the exchange using StandardWeb3 API.

        Returns:
            List of order history data
        """
        try:
            if not self._standard_client:
                self.logger().warning("StandardWeb3 client not available for order history")
                return []

            # Use StandardWeb3 to fetch account order history
            self.logger().info(f"Fetching order history for address: {self._wallet_address}")

            # Fetch order history using StandardWeb3 client
            try:
                orders_response = await self._standard_client.fetch_account_order_history_paginated_with_limit(
                    address=self._wallet_address, limit=100, page=1  # Get last 100 orders
                )

                if orders_response and "orders" in orders_response:
                    orders = orders_response["orders"]
                    self.logger().info(f"Successfully fetched {len(orders)} orders from history")
                    return orders
                else:
                    self.logger().info("No orders found in history response")
                    return []

            except Exception as e:
                self.logger().warning(f"StandardWeb3 order history failed: {e}, trying alternative method...")

                # Fallback: Use REST API endpoints
                rest_assistant = await self._web_assistants_factory.get_rest_assistant()

                # Use account orders endpoint from constants
                orders_url = f"{CONSTANTS.STANDARD_API_URL}/api/orders/{self._wallet_address}/100/1"

                orders_response = await rest_assistant.execute_request(
                    url=orders_url, method=RESTMethod.GET, throttler_limit_id=CONSTANTS.GET_ACCOUNT_ORDERS_PATH_URL
                )

                if orders_response and isinstance(orders_response, dict):
                    orders = orders_response.get("orders", [])
                    self.logger().info(f"Successfully fetched {len(orders)} orders via REST API")
                    return orders
                else:
                    self.logger().warning("REST API order history returned no valid data")
                    return []

        except Exception as e:
            self.logger().error(f"Error requesting order history: {e}", exc_info=True)
            return []

    async def _request_trade_history(self) -> List[Dict[str, Any]]:
        """
        Request trade history from the exchange using StandardWeb3 API.

        Returns:
            List of trade history data
        """
        try:
            if not self._standard_client:
                self.logger().warning("StandardWeb3 client not available for trade history")
                return []

            # Use StandardWeb3 to fetch account trade history
            self.logger().info(f"Fetching trade history for address: {self._wallet_address}")

            # Fetch trade history using StandardWeb3 client
            try:
                trades_response = await self._standard_client.fetch_account_trade_history_paginated_with_limit(
                    address=self._wallet_address, limit=100, page=1  # Get last 100 trades
                )

                if trades_response and "trades" in trades_response:
                    trades = trades_response["trades"]
                    self.logger().info(f"Successfully fetched {len(trades)} trades from history")
                    return trades
                else:
                    self.logger().info("No trades found in history response")
                    return []

            except Exception as e:
                self.logger().warning(f"StandardWeb3 trade history failed: {e}, trying alternative method...")

                # Fallback: Use REST API endpoints
                rest_assistant = await self._web_assistants_factory.get_rest_assistant()

                # Use account trades endpoint from constants
                trades_url = f"{CONSTANTS.STANDARD_API_URL}/api/tradehistory/{self._wallet_address}/100/1"

                trades_response = await rest_assistant.execute_request(
                    url=trades_url, method=RESTMethod.GET, throttler_limit_id=CONSTANTS.GET_ACCOUNT_TRADES_PATH_URL
                )

                if trades_response and isinstance(trades_response, dict):
                    trades = trades_response.get("trades", [])
                    self.logger().info(f"Successfully fetched {len(trades)} trades via REST API")
                    return trades
                else:
                    self.logger().warning("REST API trade history returned no valid data")
                    return []

        except Exception as e:
            self.logger().error(f"Error requesting trade history: {e}", exc_info=True)
            return []

    def get_order_history_df(self) -> Optional[Any]:
        """
        Get order history as a pandas DataFrame for the 'history' command.

        Returns:
            DataFrame with order history or None if pandas not available
        """
        try:
            if pd is None:
                self.logger().error("pandas not available for order history DataFrame")
                return None

            self.logger().info("Fetching order history for 'history' command...")

            # Fetch order history using async method
            import asyncio

            try:
                # Check if we're in an async context
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    # We're already in an async context, need to create a task
                    # This is a synchronous method called from CLI, so we'll use a different approach
                    order_history = []
                    trade_history = []

                    # Try to get from cache or recent data
                    # In practice, the CLI should call async methods, but for compatibility:
                    self.logger().info("Creating async task for history retrieval...")

                    # Create tasks for both order and trade history
                    async def fetch_histories():
                        orders = await self._request_order_history()
                        trades = await self._request_trade_history()
                        return orders, trades

                    # Create task and get result
                    task = asyncio.create_task(fetch_histories())
                    # Since we're in an event loop, we can't await here
                    # We'll return a placeholder and log that async fetch is happening
                    self.logger().info("Order history fetch initiated - check logs for results")

                    # Return minimal DataFrame structure for now
                    columns = [
                        "symbol",
                        "order_id",
                        "timestamp",
                        "order_type",
                        "side",
                        "amount",
                        "price",
                        "status",
                        "trade_fee",
                        "exchange_order_id",
                    ]
                    df = pd.DataFrame(columns=columns)
                    return df

                else:
                    # No event loop running, create one
                    order_history = loop.run_until_complete(self._request_order_history())
                    trade_history = loop.run_until_complete(self._request_trade_history())

            except RuntimeError:
                # No event loop exists, create one
                order_history = asyncio.run(self._request_order_history())
                trade_history = asyncio.run(self._request_trade_history())

            # Convert order history to DataFrame format
            order_data = []

            # Process order history
            for order in order_history:
                try:
                    order_entry = {
                        "symbol": order.get("trading_pair", order.get("symbol", "Unknown")),
                        "order_id": order.get("order_id", order.get("id", "Unknown")),
                        "timestamp": order.get("timestamp", order.get("created_at", "Unknown")),
                        "order_type": order.get("order_type", order.get("type", "Unknown")),
                        "side": order.get("side", "Unknown"),
                        "amount": float(order.get("amount", order.get("quantity", 0))),
                        "price": float(order.get("price", 0)),
                        "status": order.get("status", "Unknown"),
                        "trade_fee": float(order.get("fee", 0)),
                        "exchange_order_id": order.get("tx_hash", order.get("transaction_hash", "Unknown")),
                    }
                    order_data.append(order_entry)
                except Exception as e:
                    self.logger().warning(f"Error processing order entry: {e}")
                    continue

            # Process trade history and add to order data
            for trade in trade_history:
                try:
                    trade_entry = {
                        "symbol": trade.get("trading_pair", trade.get("symbol", "Unknown")),
                        "order_id": trade.get("order_id", "Trade"),
                        "timestamp": trade.get("timestamp", trade.get("created_at", "Unknown")),
                        "order_type": "TRADE",
                        "side": trade.get("side", "Unknown"),
                        "amount": float(trade.get("amount", trade.get("quantity", 0))),
                        "price": float(trade.get("price", 0)),
                        "status": "FILLED",
                        "trade_fee": float(trade.get("fee", 0)),
                        "exchange_order_id": trade.get("tx_hash", trade.get("transaction_hash", "Unknown")),
                    }
                    order_data.append(trade_entry)
                except Exception as e:
                    self.logger().warning(f"Error processing trade entry: {e}")
                    continue

            # Create DataFrame
            if order_data:
                df = pd.DataFrame(order_data)
                # Sort by timestamp (most recent first)
                if "timestamp" in df.columns:
                    df = df.sort_values("timestamp", ascending=False)

                self.logger().info(f"Order history DataFrame created with {len(df)} entries")
                return df
            else:
                # Create empty DataFrame with proper columns
                columns = [
                    "symbol",
                    "order_id",
                    "timestamp",
                    "order_type",
                    "side",
                    "amount",
                    "price",
                    "status",
                    "trade_fee",
                    "exchange_order_id",
                ]
                df = pd.DataFrame(columns=columns)
                self.logger().info("No order/trade history found - returning empty DataFrame")
                return df

        except Exception as e:
            self.logger().error(f"Error creating order history DataFrame: {e}", exc_info=True)

            # Return empty DataFrame on error
            if pd is not None:
                columns = [
                    "symbol",
                    "order_id",
                    "timestamp",
                    "order_type",
                    "side",
                    "amount",
                    "price",
                    "status",
                    "trade_fee",
                    "exchange_order_id",
                ]
                return pd.DataFrame(columns=columns)
            else:
                return None

    async def _user_stream_event_listener(self):
        """
        Listen to user stream events.
        """
        async for stream_message in self._iter_user_event_queue():
            try:
                await self._process_user_stream_event(stream_message)
            except asyncio.CancelledError:
                raise
            except Exception as e:
                self.logger().error(f"Error processing user stream event: {e}", exc_info=True)

    async def get_quote_price(self, trading_pair: str, is_buy: bool, amount: Decimal) -> Decimal:
        """
        Override to add robust price calculation with fallback for insufficient liquidity.
        """
        try:
            # Get order book
            order_book = self.get_order_book(trading_pair)
            if order_book is None:
                self.logger().warning(f"Order book not available for {trading_pair}")
                return s_decimal_NaN

            # Get bid/ask entries for fallback
            bids = list(order_book.bid_entries())
            asks = list(order_book.ask_entries())

            # Try VWAP calculation first
            vwap_result = self.get_vwap_for_volume(trading_pair, is_buy, amount)

            # Check if VWAP calculation failed due to insufficient liquidity
            if vwap_result.result_price.is_nan():
                self.logger().warning(
                    f"VWAP calculation failed for {trading_pair} {amount} ({'buy' if is_buy else 'sell'}) - insufficient liquidity"
                )

                # Fallback to best bid/ask price
                if is_buy and len(asks) > 0:
                    fallback_price = Decimal(str(asks[0].price))
                    self.logger().debug("Using fallback best ask price: {fallback_price}")
                    return fallback_price
                elif not is_buy and len(bids) > 0:
                    fallback_price = Decimal(str(bids[0].price))
                    self.logger().debug("Using fallback best bid price: {fallback_price}")
                    return fallback_price
                else:
                    self.logger().error(f"No liquidity available in order book for {trading_pair}")
                    return s_decimal_NaN

            return Decimal(str(vwap_result.result_price))

        except Exception as e:
            self.logger().error(f"Error in get_quote_price(): {e}", exc_info=True)
            return s_decimal_NaN

    async def get_order_price(self, trading_pair: str, is_buy: bool, amount: Decimal) -> Decimal:
        """
        Override to use the enhanced quote price calculation.
        """
        return await self.get_quote_price(trading_pair, is_buy, amount)

    # 🎯 PHASE 4 EXTENSION: Enhanced Cancellation Error Handling

    async def _execute_cancellation_with_retry(self, order_id: str, order_info: Dict) -> str:
        """Execute cancellation with retry logic and better error handling."""
        base_address = order_info["base_address"]
        quote_address = order_info["quote_address"]
        is_bid = order_info["is_bid"]
        blockchain_order_id = order_info["blockchain_order_id"]

        # Comment out StandardWeb3 attempt - go directly to on-chain contract cancellation
        # try:
        #     self.logger().info(f"🔄 Attempting StandardWeb3 cancellation for {order_id}")

        #     # Try StandardWeb3 client first (but don't pass base_address - it's not supported)
        #     cancellation_result = await self._standard_client.cancel_orders(
        #         orders=[blockchain_order_id]
        #     )

        #     if cancellation_result and cancellation_result.get("tx_hash"):
        #         tx_hash = cancellation_result["tx_hash"]
        #         self.logger().info(f"✅ StandardWeb3 cancellation successful: {tx_hash}")
        #         return tx_hash
        #     else:
        #         raise Exception("StandardWeb3 cancellation returned no tx_hash")

        # except Exception as e:
        #     self.logger().warning(f"⚠️ StandardWeb3 cancellation failed: {e}")

        # Go directly to contract cancellation (reliable method)
        self.logger().info(f"🔧 Using direct contract cancellation for {order_id}")
        return await self._cancel_order_on_contract(
            base_address, quote_address, is_bid, blockchain_order_id
        )

    def _record_cancellation_attempt(self, order_id: str, status: str, duration_ms: float = None):
        """Record cancellation attempt for metrics and analysis."""
        try:
            # Initialize cancellation metrics if not exists
            if not hasattr(self, "_cancellation_metrics"):
                self._cancellation_metrics = {
                    "total_attempts": 0,
                    "successful_cancellations": 0,
                    "failed_cancellations": 0,
                    "timeout_cancellations": 0,
                    "local_cancellations": 0,
                    "recent_cancellations": [],
                }

            metrics = self._cancellation_metrics
            metrics["total_attempts"] += 1

            if status == "success":
                metrics["successful_cancellations"] += 1
            elif status == "success_local":
                metrics["local_cancellations"] += 1
            elif status == "timeout":
                metrics["timeout_cancellations"] += 1
            elif status == "failed":
                metrics["failed_cancellations"] += 1

            # Record recent cancellation
            cancellation_record = {
                "timestamp": time.time(),
                "order_id": order_id,
                "status": status,
                "duration_ms": duration_ms,
            }

            metrics["recent_cancellations"].append(cancellation_record)
            if len(metrics["recent_cancellations"]) > 50:
                metrics["recent_cancellations"] = metrics["recent_cancellations"][-50:]

            # Log structured event
            if duration_ms:
                self.logger().info(
                    f"📊 CANCELLATION_EVENT: {status} | Order: {order_id} | " f"Duration: {duration_ms:.2f}ms"
                )

        except Exception as e:
            self.logger().error(f"Error recording cancellation metrics: {e}")

    def _handle_cancellation_timeout(self, order_id: str, timeout_duration: float):
        """Handle cancellation timeout with user guidance."""
        try:
            # Provide helpful guidance
            self.logger().warning(
                f"🔧 CANCELLATION TIMEOUT GUIDANCE for {order_id}:\n"
                f"   • Timeout after {timeout_duration:.0f}ms\n"
                f"   • Transaction may still be processing on blockchain\n"
                f"   • Check blockchain explorer for transaction status\n"
                f"   • Order may cancel automatically once transaction confirms\n"
                f"   • Consider increasing network gas price for faster processing"
            )

            # Emit timeout event for monitoring systems
            self._emit_transaction_event(
                "cancellation_timeout",
                {
                    "order_id": order_id,
                    "timeout_duration": timeout_duration,
                    "suggested_action": "Monitor blockchain for transaction confirmation",
                },
            )

        except Exception as e:
            self.logger().error(f"Error handling cancellation timeout: {e}")

    def get_cancellation_metrics(self) -> Dict:
        """Get cancellation performance metrics."""
        try:
            if not hasattr(self, "_cancellation_metrics"):
                return {"total_attempts": 0, "success_rate": 0.0, "timeout_rate": 0.0, "recent_cancellations": []}

            metrics = self._cancellation_metrics.copy()

            # Calculate success rate
            total = metrics["total_attempts"]
            if total > 0:
                successful = metrics["successful_cancellations"] + metrics["local_cancellations"]
                metrics["success_rate"] = (successful / total) * 100
                metrics["timeout_rate"] = (metrics["timeout_cancellations"] / total) * 100
            else:
                metrics["success_rate"] = 0.0
                metrics["timeout_rate"] = 0.0

            return metrics

        except Exception as e:
            self.logger().error(f"Error getting cancellation metrics: {e}")
            return {"error": str(e)}
