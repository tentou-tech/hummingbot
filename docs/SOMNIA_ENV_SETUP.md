# Somnia Connector Environment Setup

## Security Notice
**⚠️ NEVER commit your `.env` file to git! It contains sensitive private keys.**

## Setup Instructions

1. **Copy the example environment file:**
   ```bash
   cp .env.example .env
   ```

2. **Edit the `.env` file with your actual values:**
   ```bash
   nano .env  # or use your preferred editor
   ```

3. **Required Environment Variables:**
   - `SOMNIA_PRIVATE_KEY`: Your Ethereum wallet private key (64 hex characters)
   - `SOMNIA_RPC_URL`: Somnia network RPC endpoint (default: https://dream-rpc.somnia.network)
   - `SOMNIA_CHAIN_ID`: Somnia chain ID (default: 50312)
   - `DEFAULT_TRADING_PAIR`: Default trading pair for examples (default: ATOM-USDC)

## Usage

The Somnia example scripts will automatically load configuration from your `.env` file:

```bash
# Run the basic trading example
python scripts/somnia_examples/somnia_basic_trading.py

# Run the market maker example
python scripts/somnia_examples/somnia_market_maker.py
```

## Security Best Practices

1. **Never share your private key** with anyone
2. **Use testnet funds** for development and testing
3. **Keep your `.env` file secure** and never commit it to version control
4. **Use environment variables** in production environments instead of `.env` files
5. **Regularly rotate your keys** if they may have been compromised

## Troubleshooting

- If you get "SOMNIA_PRIVATE_KEY not found" error, ensure your `.env` file exists and contains the correct variable name
- Ensure your private key is a valid 64-character hex string (with or without '0x' prefix)
- Check that the `.env` file is in the root directory of the project
