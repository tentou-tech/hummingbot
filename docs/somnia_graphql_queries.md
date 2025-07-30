# Somnia Exchange GraphQL API Queries

This document contains the GraphQL queries discovered during API exploration of the Somnia testnet exchange (Haifu). These queries will be essential for implementing the Hummingbot connector.

## API Endpoint

```
https://haifu-release-api.up.railway.app/graphql
```

## Query Collection

### Trading Pairs Query
```graphql
query {
  spotPairss(limit: 10) {
    items {
      id
      base
      quote
    }
  }
}
```

### Tokens Query
```graphql
query {
  spotTokenss(limit: 10) {
    items {
      id
      symbol
      name
      decimals
    }
  }
}
```

### Order Book Query
```graphql
query {
  spotTickss(where: {pair: "0x2D60bB55Be15Bd4fd4E3022FC239E7F8003Ab98f"}, limit: 10) {
    items {
      pair
      isBid
      priceBN
    }
  }
}
```

### Recent Trades Query
```graphql
query {
  spotTradess(where: {pair: "0x2D60bB55Be15Bd4fd4E3022FC239E7F8003Ab98f"}, limit: 5) {
    items {
      tradeId
      maker
      taker
      isBid
      price
      timestamp
    }
  }
}
```

### Exchange Information Query
```graphql
query {
  spotExchangess {
    items {
      id
    }
  }
}
```

### Account Orders Query (Verified)
```graphql
query {
  spotOrderss(where: {account: "USER_WALLET_ADDRESS"}, limit: 10) {
    items {
      account
      orderId
      isBid
      pair {
        id
      }
      base
      baseSymbol
      quote
      quoteSymbol
      pairSymbol
      price
      priceBN
      amount
      placed
      timestamp
      txHash
      blockNumber
    }
  }
}
```

### Order History Query (Verified)
```graphql
query {
  spotOrderHistoriess(where: {account: "USER_WALLET_ADDRESS"}, limit: 10) {
    items {
      account
      blockNumber
      orderHistoryId
      orderId
      isBid
      pair
      pairSymbol
      base
      baseSymbol
      quote
      quoteSymbol
      price
      priceBN
      amount
      executed
      timestamp
      txHash
      status
    }
  }
}
```

## GraphQL Schema Observations

1. No mutation endpoints were found, suggesting orders are placed directly through smart contracts
2. No subscription endpoints were found, suggesting real-time updates come through contract events
3. The API follows a standard pattern where collection queries have an 's' suffix (e.g., spotPairss)
4. Filter parameters are passed via the 'where' argument with equality conditions
5. All queries are fully functional and tested as of July 2025
6. Rich field selection available for each entity type

## Implementation Notes

For the Hummingbot connector:

1. Use these GraphQL queries for market data retrieval
2. Implement pagination using the 'limit', 'before', and 'after' parameters when retrieving large datasets
3. Format queries with proper arguments:
   - `pair`: Trading pair contract address
   - `account`: User wallet address
   - `isBid`: Boolean to distinguish buy vs sell
4. Error handling should account for GraphQL-specific error formats
