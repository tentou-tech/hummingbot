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
    "OSMO-USDC"
]

# Error messages
ERROR_MESSAGES = {
    "insufficient_balance": "Insufficient balance to place order.",
    "invalid_order_params": "Invalid order parameters provided.",
    "order_not_found": "Order not found.",
    "connector_not_ready": "Somnia connector not ready. Please check the connection.",
    "unexpected_error": "An unexpected error occurred. Please check logs for details.",
    "network_error": "Network error connecting to Somnia blockchain."
}
