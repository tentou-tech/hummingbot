#!/usr/bin/env python3

import asyncio
import os
import sys
from hummingbot.connector.exchange.standard_testnet.standard_testnet_exchange import StandardTestnetExchange
from hummingbot.client.config.client_config_map import ClientConfigMap
from hummingbot.client.config.config_helpers import ClientConfigAdapter

async def test_connector_ready():
    """Test if the connector reports ready status properly"""
    
    # Create configuration
    client_config_map = ClientConfigAdapter(ClientConfigMap())
    
    # Initialize connector
    exchange = StandardTestnetExchange(
        client_config_map=client_config_map,
        somnia_private_key=os.getenv("STANDARD_TESTNET_PRIVATE_KEY"),
        somnia_wallet_address=os.getenv("STANDARD_TESTNET_WALLET_ADDRESS"),
        trading_pairs=["STT-USDC"]
    )
    
    print("🔄 Starting connector...")
    
    # Start the connector
    await exchange.start_network()
    
    # Wait a bit for initialization
    await asyncio.sleep(10)
    
    # Check status
    status_dict = exchange.status_dict
    ready = exchange.ready
    
    print(f"📊 Connector Status:")
    print(f"   Ready: {ready}")
    print(f"   Status Dict: {status_dict}")
    
    # Check specific status components
    print(f"\n🔍 Status Details:")
    print(f"   symbols_mapping_initialized: {status_dict.get('symbols_mapping_initialized', False)}")
    print(f"   order_books_initialized: {status_dict.get('order_books_initialized', False)}")
    print(f"   account_balance: {status_dict.get('account_balance', False)}")
    print(f"   trading_rule_initialized: {status_dict.get('trading_rule_initialized', False)}")
    print(f"   user_stream_initialized: {status_dict.get('user_stream_initialized', False)}")
    
    # Check symbol map
    symbol_map = await exchange.trading_pair_symbol_map()
    print(f"\n📋 Trading Pair Symbol Map: {dict(symbol_map)}")
    
    # Check trading rules
    print(f"\n📏 Trading Rules: {list(exchange._trading_rules.keys())}")
    
    # Check balances
    print(f"\n💰 Account Balances: {dict(exchange._account_balances)}")
    
    # Stop the connector
    await exchange.stop_network()
    
    return ready

if __name__ == "__main__":
    try:
        ready = asyncio.run(test_connector_ready())
        if ready:
            print("\n✅ SUCCESS: Connector is READY!")
            sys.exit(0)
        else:
            print("\n❌ FAILURE: Connector is NOT READY!")
            sys.exit(1)
    except Exception as e:
        print(f"\n💥 ERROR: {e}")
        sys.exit(1)
