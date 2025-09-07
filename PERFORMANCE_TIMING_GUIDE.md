# Performance Timing Implementation for Standard Exchange

## Overview
Added comprehensive performance timing to the Standard Exchange connector to diagnose why order placement is taking 1-2 seconds per order.

## 🎯 What Was Added

### 1. Performance Timing Infrastructure
- **`timing_context()`** - Context manager for timing operations with millisecond precision
- **`PerformanceTracker`** - Class to collect, analyze, and report performance metrics
- **Automatic logging** - Performance summaries logged every 5 minutes

### 2. Comprehensive Order Placement Timing
The `_place_order()` method now tracks timing for:

```
PLACE_ORDER_TOTAL              # Overall order placement time
├── UPDATE_BALANCES            # Balance fetching time
├── ADDRESS_RESOLUTION         # Token address lookup time
├── ENSURE_ALLOWANCES          # Token allowance operations
│   ├── ALLOWANCE_WEB3_SETUP   # Web3 connection setup
│   ├── ALLOWANCE_TOKEN_CALC   # Amount calculations
│   ├── ALLOWANCE_CHECK_{TOKEN} # Checking current allowance
│   └── ALLOWANCE_APPROVAL_{TOKEN} # If approval needed
│       └── ALLOWANCE_CONFIRM_{TOKEN} # Wait for tx confirmation
├── BALANCE_CHECK              # Sufficient balance validation
├── PRICE_CALCULATION          # Market order price calculation
└── BLOCKCHAIN_TRANSACTION     # Actual blockchain operations
    ├── GET_NONCE             # Nonce management
    ├── STANDARDWEB3_PLACEMENT # StandardWeb3 library method
    └── DIRECT_CONTRACT_FALLBACK # Direct contract method (if needed)
```

### 3. Balance Update Timing
The `_update_balances()` method tracks:

```
BALANCE_UPDATE_TOTAL
├── COLLECT_TOKENS            # Determine which tokens to check
├── FETCH_ALL_BALANCES       # Fetch all token balances
│   └── FETCH_BALANCE_{TOKEN} # Individual token balance calls
└── UPDATE_LOCAL_BALANCES    # Update internal balance cache
```

### 4. Individual Token Balance Timing
Each Web3 balance call tracks:

```
WEB3_BALANCE_{TOKEN}
└── WEB3_CONNECT_{TOKEN}     # Web3 RPC connection time
```

## 📊 How to Use

### Check Performance Anytime
```python
# From within Hummingbot or a script:
connector.performance_report()

# Or get raw data:
summary = connector.get_performance_summary()
```

### Automatic Logging
Performance summaries are automatically logged every 5 minutes with the prefix `⏱️`.

### Look for Timing Logs
All timing operations log start/end times with format:
```
⏱️ TIMING START: OPERATION_NAME at HH:MM:SS.mmm
⏱️ TIMING END: OPERATION_NAME at HH:MM:SS.mmm | Duration: XXX.XXms
```

### Performance Insights
The system automatically provides insights:
- ✅ Good performance: <500ms average order placement
- ℹ️ Moderate performance: 500-1000ms average
- ⚠️ Poor performance: >1000ms average (logs warning)

## 🔍 Expected Bottlenecks to Investigate

Based on the implementation, the likely causes of 1-2 second order placement are:

1. **Balance Updates** (`UPDATE_BALANCES`) - Web3 RPC calls for each token
2. **Token Allowances** (`ENSURE_ALLOWANCES`) - Especially if approval transactions needed
3. **Web3 RPC Latency** - Network calls to blockchain
4. **Transaction Confirmation** - Waiting for blockchain confirmation
5. **StandardWeb3 Library** - Internal processing time

## 📋 Next Steps

1. **Run with Performance Tracking** - Execute trading and monitor logs
2. **Identify Bottlenecks** - Look for operations >500ms consistently
3. **Optimize Based on Data**:
   - Cache balance data longer if balance updates are slow
   - Batch multiple allowance checks
   - Use faster RPC endpoints
   - Implement async/parallel processing for independent operations

## 🚀 Testing

A test script `performance_test.py` was created to validate the timing system works correctly.

## Log Examples

You'll see logs like:
```
⏱️ TIMING START: PLACE_ORDER_TOTAL (order_123) at 05:09:43.983
⏱️ TIMING START: UPDATE_BALANCES at 05:09:43.984
⏱️ TIMING END: UPDATE_BALANCES at 05:09:44.234 | Duration: 250.12ms
⏱️ TIMING START: ENSURE_ALLOWANCES_TOTAL at 05:09:44.235
⏱️ TIMING END: ENSURE_ALLOWANCES_TOTAL at 05:09:44.445 | Duration: 210.43ms
⏱️ TIMING END: PLACE_ORDER_TOTAL (order_123) at 05:09:45.123 | Duration: 1140.22ms
⏱️ PLACE ORDER PERFORMANCE: order_123 took 1140.22ms total
```

This will help pinpoint exactly where the 1-2 second delay is occurring in the order placement process.
