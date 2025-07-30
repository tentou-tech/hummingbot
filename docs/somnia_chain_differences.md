# Somnia Testnet vs Mainnet Differences

## Checklist
- [x] Chain ID differences: Testnet (TBD) vs Mainnet (NOT LAUNCHED)
- [x] Contract address differences: Testnet (TBD) vs Mainnet (NOT LAUNCHED)
- [x] API endpoint differences: Testnet (discoverable) vs Mainnet (NOT LAUNCHED)
- [x] WebSocket endpoint differences: Testnet (discoverable) vs Mainnet (NOT LAUNCHED)
- [x] EIP-712 domain config differences: Testnet (TBD) vs Mainnet (NOT LAUNCHED)
- [x] Order structure differences: Expected to be same (EVM compatibility)
- [x] Trading pair differences: Testnet (test tokens) vs Mainnet (real tokens)
- [x] Rate limit differences: Testnet (lenient) vs Mainnet (stricter expected)
- [x] Fee structure differences: Testnet (free/minimal) vs Mainnet (sub-cent fees)

## Notes

### Current Status (July 2025)
- **Testnet**: Live and operational (Shannon)
- **Mainnet**: Not launched yet - still in development roadmap

### Known Differences

#### Chain Configuration
| Aspect | Testnet (Shannon) | Mainnet | Notes |
|--------|------------------|---------|-------|
| **Launch Status** | ✅ Live | ❌ Not launched | Mainnet in roadmap but no date |
| **Chain ID** | TBD (discoverable) | TBD | Will be different |
| **Native Token** | STT (test token) | TBD (likely SOM) | Test vs production token |
| **Faucet** | Yes (Discord) | No | Test tokens vs purchased |

#### Infrastructure
| Aspect | Testnet | Mainnet | Notes |
|--------|---------|---------|-------|
| **RPC Provider** | Ankr | Likely Ankr | Same partnership expected |
| **Block Explorer** | testnet.somnia.network | TBD | Different URLs |
| **Contract Addresses** | TBD | TBD | All contracts will differ |

#### API & Development
| Aspect | Testnet | Mainnet | Notes |
|--------|---------|---------|-------|
| **Rate Limits** | Lenient (testing) | Stricter (production) | Standard practice |
| **Fees** | Minimal/Free | Sub-cent fees | Production cost model |
| **Order Structure** | EIP-712 based | Same expected | EVM compatibility |
| **Trading Pairs** | Test tokens (STT, PING, PONG) | Real tokens (ETH, USDC, etc) | Test vs production assets |

#### Performance & Features
| Aspect | Testnet | Mainnet | Notes |
|--------|---------|---------|-------|
| **TPS** | 1M+ (claimed) | 1M+ (target) | Same performance goals |
| **Finality** | Sub-second | Sub-second | Same technical specs |
| **EVM Compatibility** | Full | Full | Same development experience |

### Development Strategy

#### Testnet-First Approach
1. **Build on testnet**: Develop and test all functionality on Shannon testnet
2. **Document differences**: Track any testnet-specific behaviors or limitations
3. **Prepare for mainnet**: Build configuration switching capability
4. **Monitor announcements**: Watch for mainnet launch details

#### Configuration Management
```python
# Example approach for handling differences
DOMAINS = {
    "somnia_testnet": {
        "chain_id": TESTNET_CHAIN_ID,
        "contract": TESTNET_CONTRACT_ADDRESS,
        "base_url": TESTNET_API_URL,
        "wss_url": TESTNET_WSS_URL,
        "native_token": "STT"
    },
    "somnia": {  # Mainnet - to be filled when launched
        "chain_id": MAINNET_CHAIN_ID,
        "contract": MAINNET_CONTRACT_ADDRESS,
        "base_url": MAINNET_API_URL,
        "wss_url": MAINNET_WSS_URL,
        "native_token": "SOM"  # Assumed
    }
}
```

### Expected Mainnet Migration Considerations

#### Technical Changes
- **Chain ID**: Will be different, requiring wallet reconfiguration
- **Contract Addresses**: All exchange contracts will have new addresses
- **API Endpoints**: Likely different base URLs for mainnet services
- **Token Addresses**: Real token contracts vs test token contracts

#### Operational Changes
- **Funding**: Real tokens required instead of faucet tokens
- **Fees**: Actual transaction costs instead of free/minimal testnet fees
- **Rate Limits**: Production rate limits likely stricter than testnet
- **Error Handling**: Production environment may have different error responses

#### User Experience Changes
- **Wallet Setup**: Users need to add new network configuration
- **Token Acquisition**: Users need to obtain real tokens vs faucet tokens
- **Transaction Costs**: Users pay real fees for transactions
- **Performance**: Production load may differ from testnet performance

### Monitoring Strategy

#### Before Mainnet Launch
- [ ] Monitor Somnia Discord for mainnet announcements
- [ ] Watch for updated documentation with mainnet details
- [ ] Test connector thoroughly on testnet
- [ ] Prepare mainnet configuration templates

#### During Mainnet Launch
- [ ] Update chain ID and contract addresses immediately
- [ ] Test connectivity and basic functionality
- [ ] Monitor for any unexpected API changes
- [ ] Update user documentation with mainnet instructions

#### After Mainnet Launch
- [ ] Compare testnet vs mainnet performance
- [ ] Document any discovered differences
- [ ] Update rate limiting based on production behavior
- [ ] Gather user feedback on mainnet experience

---

## Summary

The primary difference is that **mainnet is not launched yet**. When it launches, expect:

- **Different chain ID and contract addresses** (standard for testnets vs mainnets)
- **Real tokens and fees** instead of test tokens and free transactions
- **Stricter rate limits** and production-grade infrastructure
- **Same technical capabilities** (EVM compatibility, performance, features)

The connector should be built with **configuration switching capability** to easily transition from testnet to mainnet when the time comes.
