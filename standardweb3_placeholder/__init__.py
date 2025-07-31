class StandardClient:
    def __init__(self, private_key=None, rpc_url=None):
        self.private_key = private_key
        self.rpc_url = rpc_url
        self.address = "0xmockedaddress"  # Placeholder
        print("Warning: Using minimal StandardClient implementation")

    async def get_balance(self, token=None):
        print(f"Mock: get_balance called for {token}")
        return "0.0"

    async def fetch_orderbook(self, base=None, quote=None):
        print(f"Mock: fetch_orderbook called for {base}-{quote}")
        return {"asks": [{"price": "10.0", "amount": "1.0"}], "bids": [{"price": "9.0", "amount": "1.0"}]}

    async def limit_buy(self, **kwargs):
        print(f"Mock: limit_buy called with {kwargs}")
        return "0xtx_hash_placeholder"

    async def limit_sell(self, **kwargs):
        print(f"Mock: limit_sell called with {kwargs}")
        return "0xtx_hash_placeholder"

    async def market_buy(self, **kwargs):
        print(f"Mock: market_buy called with {kwargs}")
        return "0xtx_hash_placeholder"

    async def market_sell(self, **kwargs):
        print(f"Mock: market_sell called with {kwargs}")
        return "0xtx_hash_placeholder"

    async def cancel_order(self, **kwargs):
        print(f"Mock: cancel_order called with {kwargs}")
        return "0xtx_hash_placeholder"

    async def approve_token(self, token, amount):
        print(f"Mock: approve_token called for {token}, amount: {amount}")
        return "0xtx_hash_placeholder"
