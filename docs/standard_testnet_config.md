# Standard Testnet Testnet Configuration

## Checklist
- [x] Chain ID: 50312
- [x] Native token: STT (Standard Testnet Test Token)
- [x] Block explorer URL: https://testnet.standard-testnet.network/
- [x] RPC endpoint: https://dream-rpc.standard-testnet.network
- [x] Exchange ID: standard-exchange (GraphQL identifier)
- [x] GraphQL API URL: https://haifu-release-api.up.railway.app/graphql
- [ ] WebSocket endpoints: [Not found in API - likely contract-based]
- [ ] EIP-712 domain config: [To be discovered via contract or dApp]
- [x] Trading pairs: SOL/USDC, WBTC/USDC, STT/USDC
- [ ] Rate limits: [To be discovered via API docs or dev tools]
- [ ] Fee structure: [To be discovered via dApp]

## Details

### Chain Name
Standard Testnet Testnet (Shannon)

### Chain ID
50312

### Native Token
STT (Standard Testnet Test Token)

### Block Explorer
https://testnet.standard-testnet.network/

### RPC Endpoint
https://dream-rpc.standard-testnet.network

### Exchange ID
`standard-exchange` (GraphQL identifier)

### GraphQL API URL
https://haifu-release-api.up.railway.app/graphql

### WebSocket Endpoints
Not found in API exploration. The Haifu exchange appears to use a hybrid model where:
- GraphQL API provides historical and snapshot data
- Live updates come through StandardClient event system
- No WebSocket subscriptions found in the GraphQL schema

After further research, we discovered that Standard Testnet exchange uses the Standard Exchange protocol with WebSocket endpoints at `https://ws3-standard-testnet-testnet-ponder-release.standardweb3.com`

### EIP-712 Domain Config
Not documented. Reverse engineer from contract or dApp, or request from team.

### Order Structure
From GraphQL schema analysis, orders in the system have these key components:
- `pair`: Contract address of the trading pair
- `account`: User wallet address
- `orderId`: Numeric identifier
- `isBid`: Boolean (true = buy, false = sell)
- `price`: Numeric price value
- Further details to be extracted from contract interactions

### Trading Pairs
Discovered pairs from GraphQL API:
1. SOL/USDC (ID: 0x2D60bB55Be15Bd4fd4E3022FC239E7F8003Ab98f)
   - SOL: 0xb35a7935F8fbc52fB525F16Af09329b3794E8C42 (9 decimals)
   - USDC: 0x0ED782B8079529f7385c3eDA9fAf1EaA0DbC6a17 (6 decimals)

2. WBTC/USDC (ID: 0x64E5E0793bdd0bFb7bF88343918b0a9F127aa9d1)
   - WBTC: 0x54597df4E4A6385B77F39d458Eb75443A8f9Aa9e (8 decimals)
   - USDC: 0x0ED782B8079529f7385c3eDA9fAf1EaA0DbC6a17 (6 decimals)

3. STT/USDC (ID: 0x6eC6EdEab200fb94424Bec6027024577ae79c90E)
   - STT: 0x4A3BC48C156384f9564Fd65A53a2f3D534D8f2b7 (18 decimals)
   - USDC: 0x0ED782B8079529f7385c3eDA9fAf1EaA0DbC6a17 (6 decimals)

### Rate Limits
No explicit rate limits found in GraphQL API. Most operations appear to be on-chain transactions which would be limited by blockchain throughput rather than API rate limits.

### Fee Structure
Not documented in the GraphQL API. Likely encoded in the smart contracts. Needs to be extracted from contract analysis or dApp interface.

### GraphQL Queries
See detailed GraphQL query collection in `/docs/standard-testnet_graphql_queries.md`

---
