#!/usr/bin/env python

import os
from typing import Dict, List

# Exchange information
EXCHANGE_NAME = "somnia"
DEFAULT_DOMAIN = "mainnet"  # or "testnet"

# Network configuration
SOMNIA_CHAIN_ID = 50312
SOMNIA_RPC_URL = os.getenv("SOMNIA_RPC_URL", "https://dream-rpc.somnia.network")
SOMNIA_GRAPHQL_ENDPOINT = os.getenv("SOMNIA_GRAPHQL_ENDPOINT", "https://haifu-release-api.up.railway.app/graphql")
SOMNIA_WEBSOCKET_URL = os.getenv("SOMNIA_WEBSOCKET_URL", "wss://ws3-somnia-testnet-ponder-release.standardweb3.com")

# Standard Exchange protocol endpoints
STANDARD_EXCHANGE_ADDRESS = "0x0d3251EF0D66b60C4E387FC95462Bf274e50CBE1"
STANDARD_API_URL = os.getenv("SOMNIA_STANDARD_API_URL", "https://somnia-testnet-ponder-release.standardweb3.com/")
STANDARD_WEBSOCKET_URL = os.getenv("SOMNIA_STANDARD_WEBSOCKET_URL", "https://ws1-somnia-testnet-websocket-release.standardweb3.com/")

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
    "ATOM-USDC", 
    "OSMO-USDC",
    "WBTC-USDC",
    "TOKEN1-TOKEN2"
]

# Token address mappings for Somnia testnet
TOKEN_ADDRESSES = {
    "STT": "0x4A3BC48C156384f9564Fd65A53a2f3D534D8f2b7",
    "USDC": "0x0ED782B8079529f7385c3eDA9fAf1EaA0DbC6a17", 
    "WBTC": "0x54597df4E4A6385B77F39d458Eb75443A8f9Aa9e",
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
    "ATOM": 18,
    "OSMO": 18, 
    "TOKEN1": 18,
    "TOKEN2": 18,
}

# GraphQL queries
GRAPHQL_QUERIES = {
    "orderbook": """
    query getOrderbook($baseCurrency: String!, $quoteCurrency: String!, $skip: Int!, $first: Int!) {
      sellOrders: orders(
        where: {baseToken: $baseCurrency, quoteToken: $quoteCurrency, isFilled: false, isCancelled: false, side: 1}
        orderBy: price
        orderDirection: asc
        skip: $skip
        first: $first
      ) {
        id
        price
        baseAmount
        quoteAmount
        side
      }
      buyOrders: orders(
        where: {baseToken: $baseCurrency, quoteToken: $quoteCurrency, isFilled: false, isCancelled: false, side: 0}
        orderBy: price
        orderDirection: desc
        skip: $skip
        first: $first
      ) {
        id
        price
        baseAmount
        quoteAmount
        side
      }
    }
    """,
    
    "recent_trades": """
    query getRecentTrades($baseCurrency: String!, $quoteCurrency: String!, $skip: Int!, $first: Int!) {
      trades(
        where: {baseToken: $baseCurrency, quoteToken: $quoteCurrency}
        orderBy: timestamp
        orderDirection: desc
        skip: $skip
        first: $first
      ) {
        id
        order {
          id
          side
        }
        baseToken {
          symbol
        }
        quoteToken {
          symbol
        }
        baseAmount
        quoteAmount
        price
        timestamp
      }
    }
    """,
    
    "tokens": """
    query tokens($first: Int!, $skip: Int!) {
      tokens(first: $first, skip: $skip, orderBy: tradeVolumeUSD, orderDirection: desc) {
        id
        symbol
        name
        decimals
      }
    }
    """
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
