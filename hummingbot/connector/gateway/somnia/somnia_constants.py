#!/usr/bin/env python

# Network
SOMNIA_CHAIN_ID = 50312
SOMNIA_RPC_URL = "https://dream-rpc.somnia.network"
SOMNIA_GRAPHQL_ENDPOINT = "https://haifu-release-api.up.railway.app/graphql"
SOMNIA_WEBSOCKET_URL = "wss://ws3-somnia-testnet-ponder-release.standardweb3.com"

# Standard Exchange protocol endpoints
STANDARD_EXCHANGE_ADDRESS = "0x0d3251EF0D66b60C4E387FC95462Bf274e50CBE1"  # To be verified

# Fee calculation
DEFAULT_GAS_PRICE = 10_000_000_000  # 10 gwei
DEFAULT_GAS_LIMIT_ORDER = 250_000
DEFAULT_GAS_LIMIT_CANCEL = 150_000

# Time intervals
UPDATE_ORDERBOOK_INTERVAL = 10.0  # seconds
UPDATE_BALANCES_INTERVAL = 30.0  # seconds

# API Endpoints
API_ENDPOINTS = {
    "tokens": """
    query tokens($first: Int!, $skip: Int!) {
      tokens(first: $first, skip: $skip, orderBy: tradeVolumeUSD, orderDirection: desc) {
        id
        symbol
        name
        decimals
      }
    }
    """,
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
        transaction {
          id
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
    """
}

# Trading pairs available on Somnia testnet
SOMNIA_TESTNET_TRADING_PAIRS = [
    "ATOM-USDC",
    "ATOM-OSMO",
    "OSMO-USDC",
    "STT-USDC",
    "TOKEN1-TOKEN2"  # New pair: 0x33E7fAB0a8a5da1A923180989bD617c9c2D1C493/0x9beaA0016c22B646Ac311Ab171270B0ECf23098F
]

# Token address mappings for Somnia testnet
SOMNIA_TESTNET_TOKEN_ADDRESSES = {
    "STT": "0x4A3BC48C156384f9564Fd65A53a2f3D534D8f2b7",  # Somnia Test Token (18 decimals)
    "USDC": "0x0ED782B8079529f7385c3eDA9fAf1EaA0DbC6a17",  # USD Coin (6 decimals)
    "WBTC": "0x54597df4E4A6385B77F39d458Eb75443A8f9Aa9e",  # Wrapped Bitcoin (8 decimals)
    "TOKEN1": "0x33E7fAB0a8a5da1A923180989bD617c9c2D1C493",  # Custom Token 1 (18 decimals)
    "TOKEN2": "0x9beaA0016c22B646Ac311Ab171270B0ECf23098F",  # Custom Token 2 (18 decimals)
    # Add more tokens as needed
}

# Token decimals mapping
SOMNIA_TESTNET_TOKEN_DECIMALS = {
    "STT": 18,
    "USDC": 6,
    "WBTC": 8,
    "TOKEN1": 18,
    "TOKEN2": 18,
}

# Error messages
ERROR_MESSAGES = {
    "insufficient_balance": "Insufficient balance to place order.",
    "invalid_order_params": "Invalid order parameters provided.",
    "order_not_found": "Order not found.",
    "connector_not_ready": "Somnia connector not ready. Please check the connection.",
    "unexpected_error": "An unexpected error occurred. Please check logs for details.",
    "network_error": "Network error connecting to Somnia blockchain."
}
