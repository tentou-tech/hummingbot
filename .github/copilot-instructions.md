# Hummingbot AI Coding Assistant Instructions

## Save AI Token

Use mcp #Serena to save your AI token as much as possible.

## Architecture Overview

Must read #CURSOR_VSCODE_SETUP.md
standardweb3 guide: https://github.com/standardweb3/standard.py/blob/main/README.md
Hummingbot is a Python-based algorithmic trading framework with high-performance components written in Cython (.pyx files). The codebase follows these key architectural patterns:

### Core Components
- **Connectors** (`hummingbot/connector/`): Exchange API integrations categorized by type (spot, derivative, gateway for DEX)
- **Strategies** (`hummingbot/strategy/`): Trading algorithms, with legacy strategies in Cython and new ones in Python
- **Controllers** (`controllers/`): V2 strategy components for modular trading logic (market making, directional trading)
- **Scripts** (`scripts/`): Simple strategy examples and V2 strategy implementations
- **Core** (`hummingbot/core/`): Event system, data types, utilities, with performance-critical parts in C++

### Key Patterns

#### Cython Integration
- Performance-critical components use `.pyx` files compiled to `.so` extensions
- Build with `./compile` (calls `python setup.py build_ext --inplace`)
- Always activate conda environment: `conda activate hummingbot`
- Mixed Python/Cython imports: `from .file import Class` and `from .file cimport Class`

#### Event-Driven Architecture
```python
# All core components inherit from NetworkIterator and use event system
class ExchangeConnector(ConnectorBase):
    MARKET_EVENTS = [MarketEvent.OrderFilled, MarketEvent.BuyOrderCreated, ...]
```

#### Configuration System
- Pydantic-based config classes with `BaseClientModel` inheritance
- Config files in `conf/` directory, templates in `hummingbot/templates/`
- Use `json_schema_extra={"prompt": "..."}` for CLI prompts

#### Strategy Structure
- **V1 Strategies**: Legacy Cython-based in `hummingbot/strategy/`
- **V2 Strategies**: Modern Python-based inheriting from `StrategyV2Base`
- **Controllers**: Modular components in `controllers/` for specific trading logic

## Development Workflows

### Building & Testing
```bash
# Essential build commands
./clean                    # Clean build artifacts
./compile                  # Compile Cython components
conda activate hummingbot   # Always required before building
./start                    # Launch Hummingbot CLI

# Testing
make test                  # Run pytest with coverage
make run_coverage          # Generate coverage reports
```

Cleaned build artifacts: Removed the root-owned build directory and ran clean
Activated conda environment: Used conda activate hummingbot before compilation
Fixed file ownership: Changed ownership of configuration files from root to your user account

To avoid permission issues, make sure to:

Always run installation and compilation commands as your regular user (not with sudo)
Keep the conda environment activated when working with Hummingbot
Use start to launch Hummingbot after installation

### Connector Development
New exchange connectors follow this structure:
```
hummingbot/connector/exchange/new_exchange/
├── new_exchange_exchange.py           # Main connector class
├── new_exchange_api_order_book_data_source.py
├── new_exchange_api_user_stream_data_source.py
├── new_exchange_auth.py               # API authentication
├── new_exchange_constants.py          # API endpoints, constants
├── new_exchange_utils.py              # Utility functions
└── new_exchange_web_utils.py          # Web request helpers
```

### Strategy Development
**V2 Strategy Pattern** (preferred for new development):
```python
class MyStrategyConfig(StrategyV2ConfigBase):
    script_file_name: str = os.path.basename(__file__)
    # Configuration fields with Pydantic validation

class MyStrategy(StrategyV2Base):
    def __init__(self, connectors: Dict[str, ConnectorBase], config: MyStrategyConfig):
        super().__init__(connectors, config)

    def on_tick(self):
        # Main strategy logic called every tick
```

## Project-Specific Conventions

### Import Patterns
```python
# Cython dual imports for performance
from hummingbot.core.data_type.limit_order import LimitOrder
from hummingbot.core.data_type.limit_order cimport LimitOrder

# Type checking imports to avoid circular dependencies
if TYPE_CHECKING:
    from hummingbot.client.config.config_helpers import ClientConfigAdapter
```

### Error Handling & Logging
```python
# Use class-specific loggers
@classmethod
def logger(cls):
    global connector_logger
    if connector_logger is None:
        connector_logger = logging.getLogger(__name__)
    return connector_logger
```

### Configuration Validation
```python
# Use Pydantic validators for config validation
@field_validator("trading_pair", mode="before")
@classmethod
def validate_trading_pair(cls, v, validation_info: ValidationInfo):
    # Custom validation logic
    return v
```

## Integration Points

### Exchange Connector Interface
All connectors must implement `ConnectorBase` methods:
- `_place_order()`, `_execute_cancel()` for order management
- `_update_balances()`, `_update_order_status()` for state management
- WebSocket data sources for real-time updates

### Gateway Integration (DEX)
DEX connectors use the Gateway microservice pattern:
- TypeScript Gateway service handles blockchain interactions
- Python connector communicates via HTTP API
- Located in `hummingbot/connector/gateway/`

### Data Feed Integration
```python
# Candles data for technical indicators
from hummingbot.data_feed.candles_feed.data_types import CandlesConfig
candles_config = [CandlesConfig(connector="binance", trading_pair="BTC-USDT", interval="1m")]
```

## Critical Files to Understand
- `hummingbot/connector/connector_base.pyx`: Base connector interface
- `hummingbot/strategy/strategy_v2_base.py`: Modern strategy framework
- `hummingbot/client/hummingbot_application.py`: Main application orchestrator
- `setup.py`: Cython compilation configuration
- `hummingbot/core/event/events.py`: Complete event definitions

## Performance Considerations
- Use Cython (.pyx) for computational intensive code (order book processing, price calculations)
- Event system is single-threaded - avoid blocking operations in event handlers
- WebSocket connections managed per connector with automatic reconnection
- Order book updates use high-frequency C++ data structures

When working with Hummingbot, always consider the trading context - handle partial fills, network failures, and exchange-specific quirks. The codebase prioritizes reliability and performance for live trading environments.
