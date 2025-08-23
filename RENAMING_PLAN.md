# 📋 CONNECTOR RENAMING PLAN: somnia → standard-testnet

Remember use #serena mcp

## 🎯 **TARGET CONFIGURATION**

- **Exchange Name**: `standard-testnet` (the trading platform)
- **Chain**: `somnia-testnet` (blockchain network + environment)
- **Current**: `somnia` exchange on `somnia` chain
- **Target**: `standard-testnet` exchange on `somnia-testnet` chain

---

## 📁 **PHASE 1: DIRECTORY STRUCTURE RENAMING** ✅ COMPLETED

### Main Connector Directory

- [x] `hummingbot/connector/exchange/somnia/` → `hummingbot/connector/exchange/standard_testnet/`

### Test Directory

- [x] `test/hummingbot/connector/exchange/somnia/` → `test/hummingbot/connector/exchange/standard_testnet/`

### Scripts Directory

- [x] `scripts/somnia_examples/` → `scripts/standard_testnet_examples/` (N/A - directory didn't exist)

### Configuration Files

- [x] `conf/strategies/somnia_pmm_v2_strategy.py` → `conf/strategies/standard_testnet_pmm_v2_strategy.py`

---

## 📄 **PHASE 2: FILE RENAMING** ✅ COMPLETED

### Core Connector Files

- [x] `somnia_exchange.py` → `standard_testnet_exchange.py`
- [x] `somnia_auth.py` → `standard_testnet_auth.py`
- [x] `somnia_constants.py` → `standard_testnet_constants.py`
- [x] `somnia_utils.py` → `standard_testnet_utils.py`
- [x] `somnia_web_utils.py` → `standard_testnet_web_utils.py`
- [x] `somnia_api_order_book_data_source.py` → `standard_testnet_api_order_book_data_source.py`
- [x] `somnia_api_user_stream_data_source.py` → `standard_testnet_api_user_stream_data_source.py`
- [x] `somnia_order_book.py` → `standard_testnet_order_book.py`

### Test Files

- [x] `test_somnia_exchange.py` → `test_standard_testnet_exchange.py`
- [x] `test_somnia_auth.py` → `test_standard_testnet_auth.py`
- [x] `test_somnia_web_utils.py` → `test_standard_testnet_web_utils.py`
- [x] `test_somnia_api_order_book_data_source.py` → `test_standard_testnet_api_order_book_data_source.py`
- [x] `test_somnia_api_user_stream_data_source.py` → `test_standard_testnet_api_user_stream_data_source.py`
- [x] `test_somnia_order_book.py` → `test_standard_testnet_order_book.py`

### Script Files

- [x] `scripts/somnia_examples/somnia_basic_trading.py` → `scripts/standard_testnet_examples/standard_testnet_basic_trading.py` (N/A - files didn't exist)
- [x] `scripts/somnia_examples/somnia_market_maker.py` → `scripts/standard_testnet_examples/standard_testnet_market_maker.py` (N/A - files didn't exist)

---

## 🏷️ **PHASE 3: CLASS & FUNCTION RENAMING**

### Main Classes

- [ ] `SomniaExchange` → `StandardTestnetExchange`
- [ ] `SomniaAuth` → `StandardTestnetAuth`
- [ ] `SomniaAPIOrderBookDataSource` → `StandardTestnetAPIOrderBookDataSource`
- [ ] `SomniaAPIUserStreamDataSource` → `StandardTestnetAPIUserStreamDataSource`
- [ ] `SomniaOrderBook` → `StandardTestnetOrderBook`
- [ ] `SomniaConfigMap` → `StandardTestnetConfigMap`

### Functions

- [ ] `somnia_order_type()` → `standard_testnet_order_type()`
- [ ] `generate_somnia_order_id()` → `generate_standard_testnet_order_id()`
- [ ] `to_hb_order_type(somnia_type: str)` → `to_hb_order_type(standard_testnet_type: str)`

---

## 🔧 **PHASE 4: CONSTANTS & CONFIGURATION**

### Core Constants (in constants file)

- [ ] `EXCHANGE_NAME = "somnia"` → `EXCHANGE_NAME = "standard-testnet"`
- [ ] `connector: str = "somnia"` → `connector: str = "standard-testnet"`

### Chain/Network Configuration

- [ ] Chain references: `"somnia"` → `"somnia-testnet"`
- [ ] Network references: `"testnet"` → part of `"somnia-testnet"`

### Environment Variables

- [ ] `SOMNIA_PRIVATE_KEY` → `STANDARD_TESTNET_PRIVATE_KEY`
- [ ] `SOMNIA_WALLET_ADDRESS` → `STANDARD_TESTNET_WALLET_ADDRESS`
- [ ] Keep: `SOMNIA_RPC_URL` (chain-specific, still valid)
- [ ] Keep: `SOMNIA_GRAPHQL_ENDPOINT` (chain-specific, still valid)
- [ ] Keep: `SOMNIA_WEBSOCKET_URL` (chain-specific, still valid)

---

## 📦 **PHASE 5: IMPORT STATEMENTS**

### Files with imports to update:

- [ ] `test_ready_status.py`
- [ ] `scripts/comprehensive_somnia_test_suite.py`
- [ ] `scripts/phase2_comprehensive_test.py`
- [ ] `scripts/critical_functions_test.py`
- [ ] `scripts/stt_amm_arbitrage.py`
- [ ] All test files in `test/hummingbot/connector/exchange/`

### Import Pattern Changes:

```python
# OLD
from hummingbot.connector.exchange.somnia.somnia_exchange import SomniaExchange
from hummingbot.connector.exchange.somnia import somnia_constants as CONSTANTS

# NEW
from hummingbot.connector.exchange.standard_testnet.standard_testnet_exchange import StandardTestnetExchange
from hummingbot.connector.exchange.standard_testnet import standard_testnet_constants as CONSTANTS
```

---

## 📋 **PHASE 6: CONFIGURATION FILES & STRATEGIES**

### Strategy Configuration

- [ ] Update `conf/strategies/standard_testnet_pmm_v2_strategy.py`:
  - [ ] `exchange: str = "somnia"` → `exchange: str = "standard-testnet"`
  - [ ] `markets: Dict = {"somnia": {...}}` → `markets: Dict = {"standard-testnet": {...}}`
  - [ ] Order ID prefixes: `"somnia_bid_"` → `"standard_testnet_bid_"`

### Script Updates

- [ ] `scripts/stt_amm_arbitrage.py`: `exchange = "somnia"` → `exchange = "standard-testnet"`

---

## 📚 **PHASE 7: DOCUMENTATION & METADATA**

### Documentation Files

- [ ] `docs/somnia_testnet_config.md` → `docs/standard_testnet_config.md`
- [ ] `docs/somnia_mainnet_config.md` → `docs/standard_testnet_config.md`
- [ ] Update content to reflect exchange vs chain distinction

### Environment Examples

- [ ] `.env.example`: Update variable names and documentation

### CI/CD Files

- [ ] `ci/updateManifest.sh`: Update branch name checks if needed

---

## 🔄 **PHASE 8: COMPILATION & TESTING**

### Build Process

- [ ] Run `./clean` to clear old compiled files
- [ ] Run `./compile` to build with new names
- [ ] Test import statements work correctly

### Functional Testing

- [ ] Test balance command works with `standard-testnet`
- [ ] Test history command works with `standard-testnet`
- [ ] Test strategy execution with new connector name
- [ ] Verify chain identification shows `somnia-testnet`

---

## ⚠️ **CRITICAL NOTES**

1. **Naming Convention**:

   - Exchange: `standard-testnet` (hyphenated for user-facing)
   - Python modules: `standard_testnet` (underscores for file/class names)
   - Chain: `somnia-testnet` (combined chain+network)

2. **Environment Variables Strategy**:

   - Rename user-facing config: `STANDARD_TESTNET_*`
   - Keep chain infrastructure: `SOMNIA_*` (RPC, endpoints)

3. **Backward Compatibility**:

   - Old `somnia` configurations will break
   - May need migration guide for users

4. **Order of Execution**:
   - Must complete directory/file renames before class renames
   - Must update imports after file renames
   - Compile only after all text changes complete

---

## ✅ **COMPLETION CHECKLIST**

- [x] All directories renamed
- [x] All files renamed
- [ ] All class names updated
- [ ] All function names updated
- [ ] All constants updated
- [ ] All imports updated
- [ ] All configuration files updated
- [ ] All test files updated
- [ ] All documentation updated
- [ ] Successfully compiled
- [ ] Functional testing passed

---

**STATUS**: 🟡 Phase 1-2 Complete - Ready for Phase 3-8
**NEXT**: Begin Phase 3 - Class & Function Renaming
