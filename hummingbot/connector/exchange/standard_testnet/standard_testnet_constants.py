#!/usr/bin/env python

import os
from typing import Dict, List

from hummingbot.core.api_throttler.data_types import RateLimit

# Exchange information
EXCHANGE_NAME = "standard-testnet"
DEFAULT_DOMAIN = "mainnet"  # or "testnet"

# Network configuration
SOMNIA_CHAIN_ID = 50312
SOMNIA_RPC_URL = os.getenv("SOMNIA_RPC_URL", "https://dream-rpc.somnia.network")
SOMNIA_GRAPHQL_ENDPOINT = os.getenv("SOMNIA_GRAPHQL_ENDPOINT", "https://somnia-testnet-ponder-release.standardweb3.com")
SOMNIA_WEBSOCKET_URL = os.getenv("SOMNIA_WEBSOCKET_URL", "wss://ws3-somnia-testnet-ponder-release.standardweb3.com")

# Standard Exchange protocol endpoints
STANDARD_EXCHANGE_ADDRESS = "0x0d3251EF0D66b60C4E387FC95462Bf274e50CBE1"
STANDARD_API_URL = os.getenv("SOMNIA_STANDARD_API_URL", "https://somnia-testnet-ponder-release.standardweb3.com/")
STANDARD_WEBSOCKET_URL = os.getenv("SOMNIA_STANDARD_WEBSOCKET_URL", "https://ws1-somnia-testnet-websocket-release.standardweb3.com/")

# REST API base URL
REST_API_BASE_URL = "https://somnia-testnet-ponder-release.standardweb3.com"

# GraphQL and REST API endpoints  
GRAPHQL_API_URL = os.getenv("SOMNIA_GRAPHQL_API_URL", "https://somnia-testnet-ponder-release.standardweb3.com/")
BALANCE_API_ENDPOINT = "/api/balance"  # For balance queries
MATCH_HISTORY_API_ENDPOINT = "/api/matchhistory"  # For order history

# API Endpoints
REST_API_VERSION = "v1"
WS_API_VERSION = "v1"

# Rate limits (requests per second)
MAX_REQUESTS_PER_SECOND = 10
MAX_WS_CONNECTIONS = 5

# Throttler limit IDs for API endpoints
GET_TOKEN_INFO_PATH_URL = "GET_TOKEN_INFO"
GET_ACCOUNT_INFO_PATH_URL = "GET_ACCOUNT_INFO"
GET_ORDERBOOK_PATH_URL = "GET_ORDERBOOK"
GET_PAIRS_PATH_URL = "GET_PAIRS"
GET_ACCOUNT_ORDERS_PATH_URL = "GET_ACCOUNT_ORDERS"
GET_ACCOUNT_TRADES_PATH_URL = "GET_ACCOUNT_TRADES"

# Order limits
MIN_ORDER_SIZE = 0.001
MAX_ORDER_SIZE = 1000000

# Fee configuration
DEFAULT_TRADING_FEE = 0.001  # 0.1%
DEFAULT_GAS_PRICE = 10_000_000_000  # 10 gwei
DEFAULT_GAS_LIMIT_ORDER = 250_000
DEFAULT_GAS_LIMIT_CANCEL = 150_000

# Time intervals (seconds)
UPDATE_ORDERBOOK_INTERVAL = 5.0
UPDATE_BALANCES_INTERVAL = 30.0
UPDATE_TRADING_RULES_INTERVAL = 3600.0  # 1 hour
ORDER_STATUS_UPDATE_INTERVAL = 10.0

# Trading pairs available on Somnia testnet
SOMNIA_TESTNET_TRADING_PAIRS = [
    "STT-USDC",
    "WBTC-USDC",
    "SOL-USDC",
    # Legacy pairs (may not be active)
    "ATOM-USDC", 
    "OSMO-USDC",
    "TOKEN1-TOKEN2"
]

# Token address mappings for Somnia testnet
TOKEN_ADDRESSES = {
    "STT": "0x4A3BC48C156384f9564Fd65A53a2f3D534D8f2b7",
    "USDC": "0x0ED782B8079529f7385c3eDA9fAf1EaA0DbC6a17", 
    "WBTC": "0x54597df4E4A6385B77F39d458Eb75443A8f9Aa9e",
    "SOL": "0x...",  # To be added when SOL address is available
    "ATOM": "0x...",  # To be added when available
    "OSMO": "0x...",  # To be added when available
    "TOKEN1": "0x33E7fAB0a8a5da1A923180989bD617c9c2D1C493",
    "TOKEN2": "0x9beaA0016c22B646Ac311Ab171270B0ECf23098F",
}

# Token decimals mapping
TOKEN_DECIMALS = {
    "STT": 18,
    "USDC": 6,
    "WBTC": 8,
    "SOL": 9,  # Standard SOL decimals
    "ATOM": 18,
    "OSMO": 18, 
    "TOKEN1": 18,
    "TOKEN2": 18,
}

# REST API endpoints (replacing GraphQL)
REST_API_ENDPOINTS = {
    "orderbook_ticks": "/api/orderbook/ticks/{base}/{quote}/{limit}",
    "orderbook_blocks": "/api/orderbook/blocks/{base}/{quote}/{step}/{depth}/{isSingle}",
    "trades_pair": "/api/trades/pair/{base}/{quote}/{pageSize}/{page}",
    "token_by_address": "/api/token/{address}",
    "token_by_symbol": "/api/token/symbol/{symbol}",
    "tokens_list": "/api/tokens/{pageSize}/{page}",
    "pair_by_addresses": "/api/pair/{base}/{quote}",
    "pair_by_symbols": "/api/pair/symbol/{baseSymbol}/{quoteSymbol}",
    "pairs_list": "/api/pairs/{pageSize}/{page}",
    "account_orders": "/api/orders/{address}/{pageSize}/{page}",
    "account_trades": "/api/tradehistory/{address}/{pageSize}/{page}",
    "recent_trades": "/api/trades/latest"
}

# Default parameters for API calls
API_DEFAULTS = {
    "orderbook_limit": 100,
    "orderbook_step": 1,
    "orderbook_depth": 20,
    "orderbook_single": False,
    "page_size": 50,
    "max_trades": 100
}

# WebSocket message types
WS_MESSAGE_TYPES = {
    "ORDERBOOK_UPDATE": "orderbook_update",
    "TRADE_UPDATE": "trade_update", 
    "BALANCE_UPDATE": "balance_update",
    "ORDER_UPDATE": "order_update"
}

# Error messages
ERROR_MESSAGES = {
    "insufficient_balance": "Insufficient balance to place order.",
    "invalid_order_params": "Invalid order parameters provided.",
    "order_not_found": "Order not found.",
    "connector_not_ready": "Somnia connector not ready. Please check the connection.",
    "unexpected_error": "An unexpected error occurred. Please check logs for details.",
    "network_error": "Network error connecting to Somnia blockchain.",
    "authentication_failed": "Authentication failed. Please check your credentials.",
    "rate_limit_exceeded": "Rate limit exceeded. Please wait before making more requests."
}

# Rate limits configuration for throttling
RATE_LIMITS = [
    # Generic limits for all endpoints
    RateLimit(limit_id="DEFAULT_LIMIT", limit=10, time_interval=1),
    # Order book endpoint
    RateLimit(limit_id="GET_ORDERBOOK", limit=10, time_interval=1),
    # Account info endpoint
    RateLimit(limit_id="GET_ACCOUNT_INFO", limit=5, time_interval=1),
    # Token info endpoint
    RateLimit(limit_id="GET_TOKEN_INFO", limit=10, time_interval=1),
    # Trading pairs endpoint
    RateLimit(limit_id="GET_PAIRS", limit=10, time_interval=1),
    # Order placement
    RateLimit(limit_id="POST_ORDER", limit=5, time_interval=1),
    # Order cancellation
    RateLimit(limit_id="DELETE_ORDER", limit=10, time_interval=1),
]

# Additional path constants for consistency
POST_ORDER_PATH_URL = "POST_ORDER"
DELETE_ORDER_PATH_URL = "DELETE_ORDER"
GET_ACCOUNT_PATH_URL = "GET_ACCOUNT_INFO"  # Alias for backward compatibility

# Error messages
ERROR_MESSAGES = {
    "insufficient_balance": "Insufficient balance to place order.",
    "invalid_order_params": "Invalid order parameters provided.", 
    "order_not_found": "Order not found.",
    "connector_not_ready": "Somnia connector not ready. Please check the connection.",
    "unexpected_error": "An unexpected error occurred. Please check logs for details.",
    "network_error": "Network error connecting to Somnia blockchain.",
    "authentication_failed": "Authentication failed. Please check your credentials.",
    "rate_limit_exceeded": "Rate limit exceeded. Please wait before making more requests."
}
