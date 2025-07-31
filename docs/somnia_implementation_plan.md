# Somnia Exchange Connector Implementation Plan

## Overview

The Somnia/Haifu exchange connector will leverage the `standard.py` library, an official Python client for Standard Exchange protocol. This discovery significantly simplifies our implementation, as the library already handles the complex aspects of DEX trading on the Somnia blockchain.

## Implementation Approach

### Phase 1: Library Integration & Setup

1. **Add Dependencies**
   - Add `standardweb3` to project requirements
   - Configure package installation in setup.py

2. **Create Base Connector Structure**
   - Create directory: `hummingbot/connector/gateway/somnia`
   - Create core connector files:
     - `somnia_connector.py`: Main connector class
     - `somnia_constants.py`: Constants and configuration values
     - `somnia_data_source.py`: Order book data management
     - `somnia_utils.py`: Utility functions

3. **Implement Connector Configuration**
   - Create Pydantic configuration class
   - Define required parameters:
     - RPC endpoint
     - Private key
     - API key (if needed)
     - Trading pairs

### Phase 2: Core Functionality Implementation

1. **Market Data Integration**
   - Implement order book retrieval using `StandardClient.fetch_orderbook()`
   - Set up periodic order book updates
   - Implement trade history retrieval via `fetch_recent_pair_trades_paginated()`

2. **Trading Operations**
   - Implement order placement:
     - Buy limit orders: `StandardClient.limit_buy()`
     - Sell limit orders: `StandardClient.limit_sell()`
     - Market orders: `StandardClient.market_buy()` and `StandardClient.market_sell()`
   - Implement order cancellation
   - Implement order tracking

3. **Balance Management**
   - Implement balance retrieval
   - Implement token approvals for trading
   - Set up balance update mechanism

4. **Event System Integration**
   - Map StandardClient events to Hummingbot event system
   - Implement event listeners for order updates
   - Set up contract event monitoring

### Phase 3: Testing & Refinement

1. **Unit Testing**
   - Create test fixtures with mock StandardClient
   - Test each core functionality
   - Test error handling and edge cases

2. **Integration Testing**
   - Test with testnet trading
   - Validate order placement and execution
   - Verify balance updates and trading fees

3. **Performance Optimization**
   - Optimize update frequencies
   - Implement batching for efficiency
   - Fine-tune gas settings for transactions

## Code Structure

```
hummingbot/connector/gateway/somnia/
├── somnia_connector.py         # Main connector class
├── somnia_data_source.py       # Order book management
├── somnia_constants.py         # Constants and configuration
├── somnia_utils.py             # Utility functions
└── test/                       # Test files
    ├── test_somnia_connector.py
    └── test_somnia_data_source.py
```

## Key Components

### SomniaConnector Class

```python
from standardweb3 import StandardClient
from hummingbot.connector.gateway.gateway_in_flight_order import GatewayInFlightOrder

class SomniaConnector(GatewayConnectorBase):
    def __init__(self,
                 private_key: str,
                 rpc_url: str,
                 trading_pairs: List[str],
                 trading_required: bool = True):
        super().__init__()
        self._client = StandardClient(
            private_key=private_key,
            http_rpc_url=rpc_url,
            networkName="Somnia Testnet"
        )
        # Additional initialization
```

### Order Book Management

```python
class SomniaOrderBookDataSource(OrderBookDataSource):
    async def get_new_order_book(self, trading_pair: str) -> OrderBook:
        base, quote = self._convert_trading_pair(trading_pair)
        orderbook_data = await self._connector._client.fetch_orderbook(
            base=base,
            quote=quote
        )
        return self._convert_to_order_book(orderbook_data)
```

### Order Placement

```python
async def place_order(self,
                     connector_trading_pair: str,
                     is_buy: bool,
                     amount: Decimal,
                     order_type: OrderType,
                     price: Decimal) -> Tuple[str, float]:
    """Place order using StandardClient methods"""
    base, quote = self._convert_trading_pair(connector_trading_pair)

    if order_type is OrderType.LIMIT:
        if is_buy:
            tx_hash = await self._client.limit_buy(
                base=base,
                quote=quote,
                price=str(price),
                quote_amount=str(amount * price),
                is_maker=True,
                n=0,  # To be determined
                uid=self._get_unique_id(),
                recipient=self._address
            )
        else:
            tx_hash = await self._client.limit_sell(
                base=base,
                quote=quote,
                price=str(price),
                base_amount=str(amount),
                is_maker=True,
                n=0,  # To be determined
                uid=self._get_unique_id(),
                recipient=self._address
            )
    # Handle market orders similarly
    # Return client order ID and timestamp
```

## Advantages of This Approach

1. **Reduced Development Time**: Leveraging `standard.py` eliminates the need to implement complex contract interactions and GraphQL queries from scratch.

2. **Official Integration**: Using the protocol's official library ensures compatibility and reduces the risk of errors.

3. **Future-Proofing**: The library will likely be maintained and updated as the protocol evolves.

4. **Complete Functionality**: The library already supports all trading operations needed for the connector.

## Timeline

- **Week 1**: Library integration, connector skeleton, and configuration
- **Week 2**: Market data integration and order book management
- **Week 3**: Trading operations and balance management
- **Week 4**: Testing, optimization, and documentation

## Dependencies

- `standardweb3`: Main dependency for Somnia/Haifu exchange interaction
- `web3`: For blockchain interaction (will be used by standardweb3)
- `eth_account`: For account management (will be used by standardweb3)

## References

- [StandardWeb3 GitHub Repository](https://github.com/standardweb3/standard.py)
- [Somnia Testnet Documentation](/docs/somnia_testnet_config.md)
- [Somnia GraphQL Queries](/docs/somnia_graphql_queries.md)
