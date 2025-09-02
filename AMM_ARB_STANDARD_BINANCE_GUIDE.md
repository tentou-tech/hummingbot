# Using Hummingbot's Built-in AMM Arbitrage Strategy for Standard-Binance Arbitrage

## Overview
Hummingbot already includes a powerful **AMM Arbitrage Strategy** (`amm_arb`) that's perfect for arbitraging between Standard DEX and Binance CEX. This strategy is production-tested and optimized for cross-exchange arbitrage.

## Why Use the Existing Strategy?
- ✅ **Battle-tested**: Used by hundreds of traders in production
- ✅ **Optimized**: Includes sophisticated slippage protection and risk management
- ✅ **Maintained**: Regularly updated by the Hummingbot team
- ✅ **Feature-complete**: Supports concurrent order execution, profit tracking, and more
- ✅ **Configurable**: Extensive configuration options for fine-tuning

## Strategy Features
- **Cross-exchange arbitrage** between any two connectors (CEX, DEX, AMM)
- **Slippage protection** for both markets
- **Concurrent order submission** for faster execution
- **Min profitability threshold** configuration
- **Real-time profit tracking**
- **Automatic order management** and failure handling

## Prerequisites

### 1. Exchange Setup

#### Binance API Configuration
```bash
# In Hummingbot CLI
connect binance
# Enter your API key and secret
```

#### Standard DEX Configuration
```bash
# In Hummingbot CLI
connect standard
# Enter your wallet private key
# Configure network settings
```

### 2. Verify Connections
```bash
# Check that both exchanges are connected
list connectors
balance
```

## Running AMM Arbitrage Strategy

### 1. Start Hummingbot
```bash
cd /home/thien/hummingbot
conda activate hummingbot
./start
```

### 2. Create AMM Arbitrage Strategy
In the Hummingbot CLI:
```
create amm_arb
```

### 3. Configuration Parameters
You'll be prompted to configure:

#### Core Configuration
```
Exchange 1: binance
Market 1: ETH-USDT
Exchange 2: standard  
Market 2: ETH-USDT
Order amount: 0.01
Min profitability: 0.50
```

#### Advanced Configuration
```
Market 1 slippage buffer: 0.05
Market 2 slippage buffer: 0.05
Concurrent orders submission: True
Debug price shim: False
Gateway update interval: 5.0
```

### 4. Start the Strategy
```
start
```

## Configuration Details

### Key Parameters Explained

| Parameter | Description | Recommended Value |
|-----------|-------------|-------------------|
| `order_amount` | Size of each arbitrage trade | Start with 0.01 ETH |
| `min_profitability` | Minimum profit % to execute | 0.50% (0.5%) |
| `market_1_slippage_buffer` | Binance slippage protection | 0.05% |
| `market_2_slippage_buffer` | Standard slippage protection | 0.10% (higher for DEX) |
| `concurrent_orders_submission` | Execute both sides simultaneously | True |
| `gateway_update_interval` | Price update frequency for DEX | 5.0 seconds |

### Trading Pair Considerations
- Ensure the trading pair exists on both exchanges
- Check liquidity on both sides before starting
- Popular pairs: ETH-USDT, BTC-USDT, MATIC-USDT

## Monitoring Commands

### Real-time Status
```bash
status                    # View strategy status and current opportunities
history                  # Trading history
performance              # Profit/loss analysis
balance                  # Current balances
```

### Key Metrics to Watch
- **Profitability**: Current spread between exchanges
- **Order Status**: Active buy/sell orders
- **Balance**: Ensure adequate funds on both exchanges
- **Network Status**: Monitor for connection issues

## Sample Configuration File

Create `conf/amm_arb_standard_binance.yml`:
```yaml
template_version: 28
strategy: amm_arb
market_1: binance
market_1_trading_pair: ETH-USDT
market_2: standard
market_2_trading_pair: ETH-USDT
order_amount: 0.01
min_profitability: 0.5
market_1_slippage_buffer: 0.05
market_2_slippage_buffer: 0.1
concurrent_orders_submission: true
debug_price_shim: false
gateway_update_interval: 5.0
```

To use this config:
```bash
import amm_arb_standard_binance
```

## Risk Management

### 1. Start Small
- Begin with small order amounts (0.001-0.01 ETH)
- Test thoroughly before increasing position sizes
- Monitor gas fees on Standard DEX

### 2. Balance Management
- Maintain 50/50 balance split between exchanges initially
- Monitor for inventory imbalances
- Set up balance alerts

### 3. Network Considerations
- **Gas Fees**: Factor into profitability calculations
- **Network Congestion**: May affect Standard execution times
- **Slippage**: Set appropriate buffers for both exchanges

### 4. Profitability Thresholds
- **Conservative**: 0.5-1.0% minimum profitability
- **Aggressive**: 0.2-0.5% (requires careful monitoring)
- **Factor in**: Trading fees, gas costs, slippage

## Troubleshooting

### Common Issues

#### 1. No Arbitrage Opportunities
```
Status: No arbitrage opportunities found
```
**Solutions**:
- Lower `min_profitability` threshold
- Check market liquidity on both exchanges
- Verify trading pair is active

#### 2. High Gas Fees
```
Transaction failed due to gas price
```
**Solutions**:
- Increase profitability threshold
- Monitor network congestion
- Consider time-of-day gas patterns

#### 3. Slippage Exceeded
```
Order execution failed: slippage exceeded
```
**Solutions**:
- Increase slippage buffers
- Reduce order amounts
- Check market volatility

#### 4. Balance Issues
```
Insufficient balance for arbitrage
```
**Solutions**:
- Rebalance funds between exchanges
- Transfer additional capital
- Adjust order amounts

### 5. Connection Problems
```
Gateway connection timeout
```
**Solutions**:
- Check internet connection
- Restart gateway if using DEX
- Verify API credentials

## Advanced Features

### 1. Multiple Trading Pairs
Run separate strategy instances for different pairs:
```bash
# Terminal 1: ETH-USDT arbitrage
create amm_arb_eth

# Terminal 2: BTC-USDT arbitrage  
create amm_arb_btc
```

### 2. Dynamic Configuration
Adjust parameters while running:
```bash
config min_profitability 0.3    # Lower threshold
config order_amount 0.02        # Increase size
```

### 3. Automated Rebalancing
Set up periodic balance checks and transfers between exchanges.

### 4. Performance Analytics
```bash
performance                      # View detailed P&L
export_trades                   # Export trading data
```

## Performance Optimization

### 1. Network Optimization
- Use VPS with low latency to both exchanges
- Monitor ping times to exchange APIs
- Consider geographic proximity

### 2. Strategy Tuning
- Adjust slippage buffers based on market conditions
- Optimize order sizes for available liquidity
- Fine-tune profitability thresholds

### 3. Monitoring Setup
- Set up alerts for significant opportunities
- Monitor gas price fluctuations
- Track inventory levels

## Example Trading Session

```bash
# 1. Start Hummingbot
./start

# 2. Check connections
balance

# 3. Create strategy
create amm_arb_eth_standard_binance

# 4. Monitor performance
status
# Expected output:
#   Strategy: amm_arb
#   Market 1: binance | ETH-USDT
#   Market 2: standard | ETH-USDT
#   Profitability: 0.75% (above threshold)
#   Status: Executing arbitrage...

# 5. View results
history
performance
```

## Support Resources

### Documentation
- [AMM Arbitrage Strategy Guide](https://docs.hummingbot.org/strategies/amm-arbitrage/)
- [Gateway Configuration](https://docs.hummingbot.org/gateway/)
- [Risk Management](https://docs.hummingbot.org/operation/risk-management/)

### Community
- **Discord**: https://discord.gg/hummingbot
- **Forum**: https://community.hummingbot.org
- **GitHub**: https://github.com/hummingbot/hummingbot

### Getting Help
- Use `help` command in Hummingbot CLI
- Check logs in `logs/` directory
- Report issues on GitHub

## Conclusion

The built-in AMM Arbitrage strategy is a robust, production-ready solution for Standard-Binance arbitrage. It includes all the features you need:
- Automated opportunity detection
- Risk management
- Performance tracking
- Professional-grade execution

Start with conservative settings and gradually optimize based on your risk tolerance and market conditions.

**Key Success Factors:**
1. Proper balance management between exchanges
2. Appropriate profitability thresholds accounting for all costs
3. Continuous monitoring and adjustment
4. Understanding of both exchange characteristics

This approach leverages battle-tested code used by the Hummingbot community rather than reinventing the wheel!
