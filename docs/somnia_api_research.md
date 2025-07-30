# Somnia API Research (Testnet & Mainnet)

## Checklist
- [x] Testnet Chain ID: [To be confirmed via wallet - likely discoverable by adding testnet]
- [ ] Mainnet Chain ID: [NOT LAUNCHED YET]
- [x] Native token (testnet/mainnet): STT (testnet) / TBD (mainnet)
- [x] Testnet Block explorer URL: https://testnet.somnia.network/ (Explorer section)
- [ ] Mainnet Block explorer URL: [NOT LAUNCHED YET]
- [x] Testnet RPC endpoint: https://www.ankr.com/rpc/somnia/
- [ ] Mainnet RPC endpoint: [NOT LAUNCHED YET - likely via Ankr]
- [ ] Testnet contract address: [To be discovered via dApp or Discord]
- [ ] Mainnet contract address: [NOT LAUNCHED YET]
- [ ] REST API endpoints (testnet/mainnet): [To be discovered via dev tools]
- [ ] WebSocket endpoints (testnet/mainnet): [To be discovered via dev tools]
- [x] Authentication method (EIP-712?): Yes, EVM-compatible with EIP-712 signatures
- [ ] Order structure (fields, types): [To be discovered via contract analysis]
- [ ] EIP-712 domain config (testnet/mainnet): [To be discovered]
- [ ] Order placement/cancellation endpoints: [To be discovered via dApp analysis]
- [ ] Market data endpoints: [To be discovered via dApp analysis]
- [ ] Account balance endpoints: [To be discovered via dApp analysis]
- [x] Differences between testnet and mainnet: Mainnet not launched yet

## Research Notes

### Somnia Network Overview
- **Type**: EVM-compatible Layer 1 blockchain
- **Performance**: 1,000,000+ TPS with sub-second finality
- **Fees**: Sub-cent transaction fees
- **Consensus**: Proof-of-stake with MultiStream consensus protocol

### Testnet (Shannon) Details
- **Chain Name**: Somnia Testnet (Shannon)
- **Native Token**: STT (Somnia Test Token)
- **Explorer**: https://testnet.somnia.network/
- **RPC**: https://www.ankr.com/rpc/somnia/
- **Faucet**: Available via Discord (#dev-chat channel, tag @emma_odia)
- **Developer Contact**: developers@somnia.network

### Haifu Exchange (Testnet)
- **URL**: https://testnet.haifu.fun/somnia-testnet
- **Status**: "Coming Soon!" according to testnet.somnia.network app hub
- **Interface**: Currently shows "Mobile Coming Soon - desktop only"
- **Architecture**: Likely DEX built on Somnia with EIP-712 signatures

### API Discovery Strategy
1. **Browser Dev Tools**: Monitor network requests on https://testnet.haifu.fun/somnia-testnet
2. **Contract Analysis**: Find exchange contract address via wallet interactions
3. **Discord Support**: Request technical details from Somnia dev team
4. **Documentation**: Check for updated API docs or technical specifications

### Mainnet Status
- **Launch Status**: NOT LAUNCHED YET (as of July 2025)
- **Timeline**: Part of roadmap but no specific date announced
- **Expected Differences**: Different chain ID, contract addresses, potentially different token

### Development Roadmap Progress
- ✅ Betanet: Completed
- ✅ Road to Devnet: Completed
- ✅ Devnet Launch: Completed
- ✅ Testnet: Completed (current phase)
- ⏳ Mainnet: Planned but not launched

### Key Innovations
1. **Accelerated Sequential Execution**: Compiled EVM bytecode
2. **IceDB**: Faster blockchain state database
3. **MultiStream Consensus**: Proof-of-stake BFT protocol
4. **Advanced Compression**: Handle high throughput data traffic

### Ecosystem Partners
- **Infrastructure**: Ankr (RPC services)
- **Backers**: Improbable, MSquared
- **dApps**: 30+ applications in ecosystem including Haifu exchange

---

## Action Items for Further Research

### Immediate (Phase 1)
1. Add Somnia testnet to Metamask to discover chain ID
2. Use browser dev tools on Haifu exchange to find:
   - API endpoints (REST/WebSocket)
   - Contract addresses
   - EIP-712 domain configuration
   - Order structure and formats
3. Join Discord for technical support and missing documentation

### Medium Term (Phase 2-3)
1. Analyze contract ABI once address is found
2. Test API endpoints for rate limits and responses
3. Document order placement/cancellation flows
4. Map trading pairs and fee structures

### Long Term (Phase 4-6)
1. Monitor mainnet launch announcements
2. Prepare configuration switching for mainnet
3. Update all endpoints and contracts for mainnet
4. Test connector on both networks
