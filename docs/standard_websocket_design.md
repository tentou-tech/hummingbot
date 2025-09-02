# Design Document: WebSocket Implementation for Standard Connector

## Overview

This document outlines the implementation of WebSocket functionality for the Standard connector in Hummingbot, following patterns established in the Vertex connector. The implementation will enable real-time market data and user-specific updates, reducing reliance on REST API polling and improving performance.

> **IMPORTANT NOTE**: As of August 2025, Standard protocol does not yet provide WebSocket endpoints. This design document outlines a forward-looking approach for when WebSocket functionality becomes available. The initial implementation of the Standard connector should proceed with REST API only, with WebSocket functionality to be added as an enhancement when endpoints become available.

## Architecture

The WebSocket implementation will consist of two primary components:

1. **Order Book Data Source** - For public market data (trades, order book updates)
2. **User Stream Data Source** - For private user data (orders, fills, balances)

These components will leverage Hummingbot's existing WebSocket infrastructure and follow the event-driven architecture.

## Components and Responsibilities

### 1. WebSocket Classes

| File                                      | Purpose                                                  |
| ----------------------------------------- | -------------------------------------------------------- |
| `standard_api_order_book_data_source.py`  | Manages public WebSocket connections for market data     |
| `standard_api_user_stream_data_source.py` | Manages private WebSocket connections for user data      |
| `standard_auth.py`                        | Handles authentication for private WebSocket connections |
| `standard_web_utils.py`                   | Provides WebSocket connection utilities                  |
| `standard_constants.py`                   | Defines WebSocket endpoints and message types            |

### 2. Key Classes

- **StandardAPIOrderBookDataSource**: Inherits from `OrderBookTrackerDataSource`

  - Manages connections to public WebSocket feeds
  - Subscribes to order book and trade channels
  - Processes incoming messages and converts to Hummingbot data structures

- **StandardAPIUserStreamDataSource**: Inherits from `UserStreamTrackerDataSource`
  - Manages connections to private WebSocket feeds
  - Authenticates using StandardAuth
  - Processes user-specific events (orders, fills, balance updates)

## Implementation Details

### WebSocket Endpoints and Subscriptions

```python
# In standard_constants.py
WS_URL = "wss://api.standard.tech/ws"  # To be confirmed with Standard docs
WS_SUBSCRIBE_METHOD = "subscribe"

# Public channels
ORDERBOOK_CHANNEL = "orderbook"
TRADES_CHANNEL = "trades"

# Private channels
ORDERS_CHANNEL = "orders"
FILLS_CHANNEL = "fills"
BALANCES_CHANNEL = "balances"

# Message types
DIFF_EVENT_TYPE = "diff"
TRADE_EVENT_TYPE = "trade"
ORDER_EVENT_TYPE = "order"
FILL_EVENT_TYPE = "fill"
BALANCE_EVENT_TYPE = "balance"
```

### Connection and Subscription Flow

1. **Connection Establishment**:

   - Create WebSocket connection using `WSAssistant` from `web_assistants_factory`
   - Configure ping interval (30 seconds recommended) for connection maintenance

2. **Subscription Process**:

   - Public data: Subscribe to orderbook and trades channels for each trading pair
   - Private data: Subscribe to orders, fills, and balances channels with authentication

3. **Message Processing**:
   - Implement message handlers based on message type
   - Convert exchange-specific formats to Hummingbot data structures
   - Route messages to appropriate queues (order book diffs, trades, user events)

### Authentication Mechanism

```python
# In standard_auth.py
class StandardAuth:
    def __init__(self, api_key: str, api_secret: str):
        self._api_key = api_key
        self._api_secret = api_secret

    async def get_ws_auth_params(self) -> Dict[str, Any]:
        # Generate authentication parameters for WebSocket connection
        timestamp = int(time.time() * 1000)
        signature = self._generate_signature(timestamp)

        return {
            "api_key": self._api_key,
            "timestamp": timestamp,
            "signature": signature
        }

    def _generate_signature(self, timestamp: int) -> str:
        # Generate signature based on Standard's authentication requirements
        # Implement according to Standard WebSocket API documentation
        pass
```

### Error Handling and Reconnection

- Implement heartbeat mechanism to detect disconnections
- Add reconnection logic with exponential backoff
- Handle message parsing errors gracefully
- Log reconnection attempts and failures

## Integration with Existing Connector

The WebSocket components will be integrated with the existing StandardExchange connector:

```python
# In standard_exchange.py
class StandardExchange(ExchangePyBase):
    def __init__(self, ...):
        # ...existing initialization...

        # Initialize order book tracker with WebSocket data source
        self._order_book_tracker = OrderBookTracker(
            data_source=StandardAPIOrderBookDataSource(
                trading_pairs=trading_pairs,
                connector=self,
                api_factory=self._web_assistants_factory
            ),
            trading_pairs=trading_pairs
        )

        # Initialize user stream tracker with WebSocket data source
        self._user_stream_tracker = UserStreamTracker(
            data_source=StandardAPIUserStreamDataSource(
                auth=self._auth,
                connector=self,
                api_factory=self._web_assistants_factory
            )
        )
```

## WebSocket Message Handling

### Public Data Processing

```python
# In standard_api_order_book_data_source.py
async def _process_websocket_messages(self, websocket: WSAssistant):
    async for ws_response in websocket.iter_messages():
        data = ws_response.data
        msg_type = data.get("type")

        if msg_type == DIFF_EVENT_TYPE:
            # Process order book diff message
            trading_pair = self._get_trading_pair_from_message(data)
            order_book_message = self._convert_to_order_book_diff(data)
            output_queue = self._message_queue[trading_pair]
            await output_queue.put(order_book_message)

        elif msg_type == TRADE_EVENT_TYPE:
            # Process trade message
            trading_pair = self._get_trading_pair_from_message(data)
            trade_message = self._convert_to_trade_message(data)
            output_queue = self._message_queue[trading_pair]
            await output_queue.put(trade_message)
```

### Private Data Processing

```python
# In standard_api_user_stream_data_source.py
async def _process_websocket_messages(self, websocket: WSAssistant):
    async for ws_response in websocket.iter_messages():
        data = ws_response.data
        event_type = data.get("type")

        if event_type == ORDER_EVENT_TYPE:
            # Process order update message
            order_update = self._convert_to_order_update(data)
            self._order_updates_queue.put_nowait(order_update)

        elif event_type == FILL_EVENT_TYPE:
            # Process trade fill message
            trade_update = self._convert_to_trade_update(data)
            self._trade_updates_queue.put_nowait(trade_update)

        elif event_type == BALANCE_EVENT_TYPE:
            # Process balance update message
            balance_update = self._convert_to_balance_update(data)
            self._balance_updates_queue.put_nowait(balance_update)
```

## Implementation Timeline

### Phase 0 - Initial REST Implementation (Current Priority)
   - Implement Standard connector using REST API only
   - Set up polling mechanisms for order book, trades, and user data
   - Ensure all trading functionality works reliably with REST endpoints
   - This phase should be completed first, allowing the connector to be used immediately

### Phase 1 - Setup and Constants (When WebSocket Available)
   - Create WebSocket constants file with endpoints and message types
   - Implement authentication for WebSocket connections

### Phase 2 - Public Data Source
   - Implement OrderBookDataSource with WebSocket connection
   - Add subscription and message processing logic
   - Test with real-time market data
   - Maintain REST API as fallback

### Phase 3 - User Stream Data Source
   - Implement UserStreamDataSource with authentication
   - Add user-specific subscription and message processing
   - Test with user order and balance updates
   - Maintain REST API as fallback

### Phase 4 - Integration and Testing
   - Integrate WebSocket components with StandardExchange connector
   - Add comprehensive error handling and reconnection logic
   - Conduct performance and stability testing
   - Implement graceful fallback to REST API when WebSocket is unavailable

## Required Standard API Features

To implement this WebSocket functionality, the Standard API must support:

1. WebSocket connection endpoints for market and user data
2. Channel-based subscription model
3. Authentication mechanism for private WebSocket feeds
4. Real-time order book updates (snapshot and diffs)
5. Trade updates for market data
6. Order, fill, and balance updates for user data

> **Note**: These features are not yet available in the Standard API. The connector should be initially implemented using REST API, with WebSocket functionality added when these features become available.

## REST Implementation (Current Approach)

Until WebSocket endpoints are available, the Standard connector should implement:

### Order Book Data Source
```python
# Example REST-based implementation
class StandardAPIOrderBookDataSource(OrderBookTrackerDataSource):
    async def get_new_order_book(self, trading_pair: str) -> OrderBook:
        # Fetch snapshot via REST API
        snapshot = await self._request_order_book_snapshot(trading_pair)
        # Convert to order book
        return self.order_book_create_function()

    # Instead of WebSocket listening, use polling
    async def listen_for_order_book_snapshots(self, ev_loop, output: asyncio.Queue):
        while True:
            try:
                for trading_pair in self._trading_pairs:
                    snapshot_msg = await self._order_book_snapshot(trading_pair)
                    output.put_nowait(snapshot_msg)
                await asyncio.sleep(self.SNAPSHOT_INTERVAL_SECONDS)
            except asyncio.CancelledError:
                raise
            except Exception:
                self.logger().error("Unexpected error listening for order book snapshots.", exc_info=True)
                await asyncio.sleep(5.0)
```

### User Data Updates
```python
# In standard_exchange.py
async def _update_order_status(self):
    # Poll for order updates via REST API
    # Process order updates

async def _update_balances(self):
    # Poll for balance updates via REST API
    # Process balance updates
```

## Conclusion

This WebSocket implementation will significantly improve the Standard connector's performance and reduce API load by replacing polling with real-time updates when WebSocket endpoints become available. In the meantime, a REST-based implementation will provide full functionality for the Standard connector.

The implementation should follow a phased approach:
1. First implement the connector using REST API only
2. Add WebSocket functionality as an enhancement when endpoints become available
3. Maintain REST functionality as a fallback mechanism

Following the established Vertex connector pattern ensures consistency with Hummingbot's architecture while providing the specific functionality required for the Standard protocol.
