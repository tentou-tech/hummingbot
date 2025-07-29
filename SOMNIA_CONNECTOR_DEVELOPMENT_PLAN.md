# Somnia Testnet Connector Development Plan

## Overview
This document outlines the step-by-step development plan for implementing a Hummingbot connector for the Somnia testnet exchange (https://testnet.haifu.fun/somnia-testnet). Since Somnia is an EVM-based blockchain, we will base our implementation on the **Vertex connector** pattern rather than centralized exchange patterns like Binance.

## Architecture Decision

### Why Vertex Pattern vs Binance Pattern?
- **Somnia**: EVM-based blockchain with smart contracts
- **Vertex**: EVM-compatible DEX on Arbitrum using EIP-712 signatures
- **Binance**: Centralized exchange with REST API + API keys

**✅ Vertex Pattern (Chosen):**
- EIP-712 signature-based authentication
- Private key wallet integration
- On-chain order verification
- WebSocket + REST hybrid architecture

**❌ Binance Pattern (Not suitable):**
- API key + secret authentication
- Server-side order management
- Traditional REST API rate limiting

## Development Phases

## Phase 1: Research & Discovery 🔍

### 1.1 Somnia Network Research (Both Chains)
**Tasks:**
- [ ] **Investigate Somnia blockchain details for BOTH chains**
  - **Testnet Chain ID** and **Mainnet Chain ID**
  - Native token (likely ETH or custom token) - verify for both
  - **Testnet Block explorer URLs** and **Mainnet Block explorer URLs**
  - **Testnet RPC endpoints** and **Mainnet RPC endpoints**
  - Network configurations differences between testnet/mainnet

- [ ] **Analyze Haifu exchange architecture on BOTH chains**
  - **TESTNET**: Visit https://testnet.haifu.fun/somnia-testnet
  - **MAINNET**: Find mainnet interface URL (if available)
  - Check browser developer tools for API calls on both
  - Document REST API endpoints for testnet AND mainnet
  - Identify WebSocket streams for both networks
  - Find smart contract addresses for testnet AND mainnet

- [ ] **Document API structure for BOTH chains**
  - Authentication method (likely EIP-712) - verify same for both
  - Order placement endpoints (testnet vs mainnet differences)
  - Market data feeds (different URLs for each chain)
  - Account balance queries (chain-specific configurations)
  - Order cancellation process (verify consistency across chains)

**Deliverables:**
- `docs/somnia_api_research.md` - Complete API documentation for BOTH chains
- `docs/somnia_testnet_config.md` - Testnet-specific configuration details
- `docs/somnia_mainnet_config.md` - Mainnet-specific configuration details
- `docs/somnia_chain_differences.md` - Key differences between testnet and mainnet

### 1.2 Smart Contract Analysis (Dual Chain)
**Tasks:**
- [ ] **Find exchange contract addresses for BOTH chains**
  - Testnet exchange contract address
  - Mainnet exchange contract address (if available)
- [ ] **Analyze contract ABI for BOTH chains**
  - Verify ABI compatibility between testnet/mainnet
  - Document any differences in contract interfaces
- [ ] **Document EIP-712 domain configuration for BOTH chains**
  - Testnet domain configuration (name, version, chainId, verifyingContract)
  - Mainnet domain configuration (likely different chainId and contract)
- [ ] **Identify order structure requirements**
  - Verify order structure consistency across both chains
  - Document any chain-specific requirements

## Phase 2: Project Structure Setup 🏗️

### 2.1 Create Connector Directory Structure
```bash
mkdir -p hummingbot/connector/exchange/somnia
```

**Files to create:**
- [ ] `__init__.py`
- [ ] `somnia_constants.py` - Network config, endpoints, rate limits
- [ ] `somnia_auth.py` - EIP-712 signature authentication
- [ ] `somnia_eip712_structs.py` - Order/cancellation structures
- [ ] `somnia_utils.py` - Helper functions
- [ ] `somnia_web_utils.py` - HTTP request utilities
- [ ] `somnia_exchange.py` - Main connector class
- [ ] `somnia_api_order_book_data_source.py` - Market data WebSocket
- [ ] `somnia_api_user_stream_data_source.py` - User account updates
- [ ] `somnia_order_book.py` - Order book implementation

### 2.2 Copy Vertex Template Files
**Tasks:**
- [ ] Copy Vertex connector files as templates
- [ ] Rename all classes from `Vertex` to `Somnia`
- [ ] Update import statements
- [ ] Remove Vertex-specific logic

## Phase 3: Core Configuration Implementation ⚙️

### 3.1 Implement `somnia_constants.py`
**Based on dual-chain research from Phase 1:**

```python
# Network Configuration - BOTH CHAINS
DEFAULT_DOMAIN = "somnia"           # Mainnet
TESTNET_DOMAIN = "somnia_testnet"   # Testnet (PRIMARY for development)

# API Base URLs - Research both testnet and mainnet
BASE_URLS = {
    DEFAULT_DOMAIN: "https://api.haifu.fun/v1",           # Mainnet API (to be determined)
    TESTNET_DOMAIN: "https://testnet-api.haifu.fun/v1",   # Testnet API (to be determined)
}

# WebSocket URLs - Research both chains
WSS_URLS = {
    DEFAULT_DOMAIN: "wss://ws.haifu.fun/v1/ws",           # Mainnet WS (to be determined)
    TESTNET_DOMAIN: "wss://testnet-ws.haifu.fun/v1/ws",   # Testnet WS (to be determined)
}

# Blockchain Configuration - CRITICAL: Get both chain configs
CONTRACTS = {
    DEFAULT_DOMAIN: "0x...",     # Somnia mainnet exchange contract (research needed)
    TESTNET_DOMAIN: "0x...",     # Somnia testnet exchange contract (PRIMARY FOCUS)
}

CHAIN_IDS = {
    DEFAULT_DOMAIN: ???,         # Somnia mainnet chain ID (research needed)
    TESTNET_DOMAIN: ???,         # Somnia testnet chain ID (CRITICAL for development)
}

# Rate Limits - May differ between testnet/mainnet
RATE_LIMITS = [
    RateLimit(limit_id="REQUEST_WEIGHT", limit=1200, time_interval=60),
    # Add testnet-specific limits (often more lenient)
    # Add mainnet-specific limits (often stricter)
]

# Order States - Verify consistency across both chains
ORDER_STATE = {
    "NEW": OrderState.OPEN,
    "FILLED": OrderState.FILLED,
    "CANCELED": OrderState.CANCELED,
    # Add Somnia-specific states for both chains
}
```

**Tasks:**
- [ ] Research and fill in all URL endpoints for BOTH chains
- [ ] Determine chain IDs for testnet AND mainnet
- [ ] Find exchange contract addresses for BOTH chains
- [ ] Document API rate limits (testnet vs mainnet differences)
- [ ] Define order states mapping (verify consistency across chains)
- [ ] **PRIORITY**: Focus on testnet configuration for initial development

### 3.2 Implement `somnia_eip712_structs.py`
**Based on Somnia's order format:**

```python
from eip712_structs import Address, Array, Bytes, EIP712Struct, Int, String, Uint

class Order(EIP712Struct):
    # Structure to be determined based on Somnia API
    sender = Address()
    trading_pair = String()  # or separate base/quote
    side = String()          # "BUY" or "SELL"
    amount = Uint(256)
    price = Uint(256)
    expiration = Uint(64)
    nonce = Uint(64)

class Cancellation(EIP712Struct):
    # Structure to be determined
    sender = Address()
    order_ids = Array(Bytes(32))
    nonce = Uint(64)
```

**Tasks:**
- [ ] Research Somnia's exact order structure
- [ ] Implement EIP-712 structs matching Somnia format
- [ ] Add validation methods

### 3.3 Implement `somnia_auth.py`
**EIP-712 signature authentication for BOTH chains:**

```python
class SomniaAuth(AuthBase):
    def __init__(self, somnia_address: str, somnia_private_key: str, domain: str = CONSTANTS.TESTNET_DOMAIN):
        self.sender_address = somnia_address
        self.private_key = somnia_private_key
        self.domain = domain  # Allow switching between testnet/mainnet

    def sign_payload(self, payload: Any, contract: str, chain_id: int) -> Tuple[str, str]:
        # EIP-712 signing implementation - should work for both chains
        domain = make_domain(
            name="SomniaExchange",  # To be researched (may differ by chain)
            version="1.0.0",        # To be researched (verify same for both)
            chainId=chain_id,       # DIFFERENT for testnet vs mainnet
            verifyingContract=contract  # DIFFERENT contract addresses
        )
        # Implement signing logic similar to Vertex

    def get_chain_config(self):
        """Get the appropriate chain configuration based on domain"""
        return {
            'chain_id': CONSTANTS.CHAIN_IDS[self.domain],
            'contract': CONSTANTS.CONTRACTS[self.domain],
            'base_url': CONSTANTS.BASE_URLS[self.domain],
            'wss_url': CONSTANTS.WSS_URLS[self.domain]
        }
```

**Tasks:**
- [ ] Implement EIP-712 domain configuration for BOTH chains
- [ ] Add signature generation methods (testnet-compatible first)
- [ ] Add digest generation for order tracking
- [ ] **Add chain switching capability** for easy testnet/mainnet toggling
- [ ] Verify signature compatibility across both chains

## Phase 4: Core Exchange Implementation 💼

### 4.1 Implement `somnia_exchange.py`
**Main connector class based on Vertex pattern:**

```python
class SomniaExchange(ExchangePyBase):
    def __init__(
        self,
        client_config_map: "ClientConfigAdapter",
        somnia_address: str,
        somnia_private_key: str,
        trading_pairs: Optional[List[str]] = None,
        trading_required: bool = True,
        domain: str = CONSTANTS.DEFAULT_DOMAIN,
    ):
        # Initialize with wallet credentials instead of API keys
```

**Key methods to implement:**
- [ ] `_place_order()` - Submit signed orders to Somnia
- [ ] `_place_cancel()` - Cancel orders using signatures
- [ ] `_update_balances()` - Query account balances
- [ ] `_request_order_status()` - Check order status
- [ ] `_format_trading_rules()` - Parse trading pair rules

**Tasks:**
- [ ] Adapt Vertex exchange class for Somnia
- [ ] Implement order placement with EIP-712 signatures
- [ ] Add balance tracking
- [ ] Implement order status polling

### 4.2 Implement WebSocket Data Sources

#### `somnia_api_order_book_data_source.py`
**Tasks:**
- [ ] Implement order book snapshot retrieval
- [ ] Add WebSocket subscription for order book updates
- [ ] Process real-time trade data
- [ ] Handle connection management

#### `somnia_api_user_stream_data_source.py`
**Tasks:**
- [ ] Subscribe to user-specific WebSocket streams
- [ ] Process order update events
- [ ] Handle balance change notifications
- [ ] Process trade execution events

## Phase 5: Testing & Integration 🧪

### 5.1 Unit Testing
**Create test files:**
- [ ] `test/hummingbot/connector/exchange/somnia/test_somnia_exchange.py`
- [ ] `test/hummingbot/connector/exchange/somnia/test_somnia_auth.py`
- [ ] `test/hummingbot/connector/exchange/somnia/test_somnia_order_book_data_source.py`

**Tasks:**
- [ ] Mock API responses for testing
- [ ] Test EIP-712 signature generation
- [ ] Test order placement and cancellation
- [ ] Test WebSocket message processing

### 5.2 Integration with Hummingbot Core

#### Configuration Integration
**Tasks:**
- [ ] Add Somnia to `hummingbot/client/config/config_helpers.py`
- [ ] Create config template `hummingbot/templates/conf_exchange_somnia.yml`
- [ ] Add to connector imports in `__init__.py` files

#### Trading Fee Configuration
**Tasks:**
- [ ] Research Somnia trading fees
- [ ] Add fee configuration to schema files
- [ ] Test fee calculation

### 5.3 Testnet Validation (Primary Focus)
**Tasks:**
- [ ] **Create testnet wallet with test funds**
  - Set up Metamask/wallet for Somnia testnet
  - Get testnet tokens from faucet (if available)
  - Verify wallet connection to Somnia testnet
- [ ] **Test connection to Somnia testnet**
  - Verify API endpoints work with testnet
  - Test WebSocket connections to testnet
  - Validate EIP-712 signatures on testnet
- [ ] **Validate order placement on testnet**
  - Place test orders with small amounts
  - Verify order appears in exchange interface
  - Test different order types (limit, market)
- [ ] **Test order cancellation on testnet**
  - Cancel pending orders
  - Verify cancellation signatures work
  - Test bulk cancellation
- [ ] **Verify balance updates on testnet**
  - Monitor balance changes after trades
  - Test WebSocket balance updates
  - Verify accuracy against blockchain state
- [ ] **Test WebSocket reconnection on testnet**
  - Simulate connection drops
  - Verify automatic reconnection
  - Test data consistency after reconnect
- [ ] **Prepare for mainnet transition**
  - Document differences found during testnet testing
  - Create mainnet configuration checklist
  - Plan mainnet deployment strategy

## Phase 6: Documentation & Deployment 📚

### 6.1 Documentation
**Tasks:**
- [ ] Create user setup guide
- [ ] Document wallet configuration process
- [ ] Add troubleshooting section
- [ ] Create API reference documentation

### 6.2 Code Review & Optimization
**Tasks:**
- [ ] Code review against Hummingbot standards
- [ ] Performance optimization
- [ ] Error handling improvements
- [ ] Logging enhancements

### 6.3 Production Readiness
**Tasks:**
- [ ] Mainnet configuration (when available)
- [ ] Security audit of private key handling
- [ ] Rate limiting validation
- [ ] Connection stability testing

## Development Workflow

### Daily Development Process
1. **Morning Setup:**
   - Review current phase tasks
   - Pull latest changes from repository
   - Activate conda environment: `conda activate hummingbot`

2. **Development Cycle:**
   - Work on current phase tasks
   - Test changes with: `./compile && ./start`
   - Commit progress regularly

3. **Testing:**
   - Run unit tests: `make test`
   - Test on Somnia testnet
   - Document any issues

### Git Workflow
```bash
# Create feature branch for each phase
git checkout -b feature/somnia-phase-1-research
git checkout -b feature/somnia-phase-2-structure
git checkout -b feature/somnia-phase-3-config
# etc.
```

## Risk Mitigation

### Technical Risks
- **API Changes**: Somnia API might change during development
  - *Mitigation*: Regular API monitoring, flexible architecture
- **EIP-712 Compatibility**: Signature format might differ from Vertex
  - *Mitigation*: Thorough testing, reference implementation analysis
- **WebSocket Stability**: Connection issues with Somnia WebSocket
  - *Mitigation*: Robust reconnection logic, fallback mechanisms

### Timeline Risks
- **API Documentation Delay**: Waiting for complete API docs
  - *Mitigation*: Reverse engineer from web interface, contact Somnia team
- **Testing Limitations**: Limited testnet funds or functionality
  - *Mitigation*: Request testnet support, implement comprehensive mocking

## Success Criteria

### Phase Completion Criteria
- [ ] **Phase 1**: Complete API documentation and network configuration
- [ ] **Phase 2**: All connector files created with basic structure
- [ ] **Phase 3**: Core configuration working with valid signatures
- [ ] **Phase 4**: Order placement and cancellation working on testnet
- [ ] **Phase 5**: Full integration with passing tests
- [ ] **Phase 6**: Production-ready connector with documentation

### Final Success Metrics
- [ ] Successfully place and cancel orders on Somnia testnet
- [ ] Real-time balance and order status updates working
- [ ] WebSocket connections stable with reconnection
- [ ] Integration tests passing
- [ ] User documentation complete
- [ ] Code review approved

## Resources & References

### Hummingbot References
- **Vertex Connector**: `/hummingbot/connector/exchange/vertex/`
- **Exchange Base**: `/hummingbot/connector/exchange_py_base.py`
- **Connector Base**: `/hummingbot/connector/connector_base.pyx`

### External References
- **Somnia Testnet**: https://testnet.haifu.fun/somnia-testnet
- **EIP-712 Standard**: https://eips.ethereum.org/EIPS/eip-712
- **Hummingbot Documentation**: https://docs.hummingbot.org/

## Next Steps

1. **Start with Phase 1**: Begin research and discovery **for BOTH chains**
2. **Set up development environment**: Ensure conda environment is ready
3. **Create project branch**: `git checkout -b feature/somnia-connector`
4. **Begin dual-chain API research**:
   - **PRIMARY**: Analyze Somnia testnet interface at https://testnet.haifu.fun/somnia-testnet
   - **SECONDARY**: Research mainnet configuration (if available)
5. **Focus on testnet first**: All development and testing on testnet before mainnet

---

*This document will be updated as we progress through each phase and discover new requirements.*
