#!/usr/bin/env python3
"""
Diagnostic script to test balance functionality on server.
This will help identify why balance updates are failing silently.
"""
import asyncio
import sys
import os
import traceback
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

# Set up environment
os.environ.setdefault('PYTHONPATH', str(project_root))

async def test_balance_diagnostics():
    """Test balance functionality step by step to identify issues."""
    
    print("🔍 BALANCE DIAGNOSTIC TEST")
    print("=" * 50)
    
    try:
        # Step 1: Test environment variables
        print("\n1. Testing Environment Variables...")
        
        from dotenv import load_dotenv
        load_dotenv()
        
        wallet_address = os.getenv('SOMNIA_WALLET_ADDRESS')
        private_key = os.getenv('SOMNIA_PRIVATE_KEY')
        
        if not wallet_address:
            print("❌ SOMNIA_WALLET_ADDRESS not found in .env")
            return
        if not private_key:
            print("❌ SOMNIA_PRIVATE_KEY not found in .env")
            return
            
        print(f"✅ Wallet address: {wallet_address}")
        print(f"✅ Private key: {'*' * 10} (length: {len(private_key)})")
        
        # Step 2: Test basic imports
        print("\n2. Testing Imports...")
        
        try:
            from hummingbot.connector.exchange.standard.standard_exchange import StandardExchange
            print("✅ StandardExchange import successful")
        except Exception as e:
            print(f"❌ Import failed: {e}")
            traceback.print_exc()
            return
            
        # Step 3: Test Web3 connectivity
        print("\n3. Testing Web3 Connectivity...")
        
        try:
            from web3 import Web3
            rpc_url = "https://dream-rpc.somnia.network"
            w3 = Web3(Web3.HTTPProvider(rpc_url))
            
            if w3.is_connected():
                print(f"✅ Connected to Somnia RPC: {rpc_url}")
                latest_block = w3.eth.block_number
                print(f"✅ Latest block: {latest_block}")
            else:
                print(f"❌ Failed to connect to Somnia RPC: {rpc_url}")
                return
        except Exception as e:
            print(f"❌ Web3 connection failed: {e}")
            traceback.print_exc()
            return
            
        # Step 4: Test StandardWeb3 client
        print("\n4. Testing StandardWeb3 Client...")
        
        try:
            from hummingbot.connector.exchange.standard.standard_exchange import StandardExchange
            from hummingbot.client.config.client_config_map import ClientConfigMap
            
            config_map = ClientConfigMap()
            
            # Create connector
            connector = StandardExchange(
                client_config_map=config_map,
                somnia_wallet_address=wallet_address,
                somnia_private_key=private_key,
                trading_pairs=[],
                trading_required=False,
                domain='mainnet'
            )
            
            print("✅ Connector created successfully")
            
            # Test StandardWeb3 client
            if connector._standard_client:
                print("✅ StandardWeb3 client initialized")
            else:
                print("❌ StandardWeb3 client not available")
                return
                
        except Exception as e:
            print(f"❌ Connector creation failed: {e}")
            traceback.print_exc()
            return
            
        # Step 5: Test balance fetching step by step
        print("\n5. Testing Balance Fetching...")
        
        try:
            # Test each token individually
            tokens = ["SOMNIA", "STT", "USDC"]
            
            for token in tokens:
                print(f"\n  Testing {token}...")
                try:
                    # Test Web3 balance method
                    balance = await connector._get_token_balance_web3(token)
                    print(f"  ✅ {token}: {balance}")
                except Exception as token_error:
                    print(f"  ❌ {token} failed: {token_error}")
                    traceback.print_exc()
                    
        except Exception as e:
            print(f"❌ Balance testing failed: {e}")
            traceback.print_exc()
            return
            
        # Step 6: Test full balance update
        print("\n6. Testing Full Balance Update...")
        
        try:
            await connector._update_balances()
            
            balances = connector.get_all_balances()
            print(f"✅ Full balance update completed")
            print(f"✅ Retrieved {len(balances)} token balances:")
            for token, balance in balances.items():
                print(f"    {token}: {balance}")
                
        except Exception as e:
            print(f"❌ Full balance update failed: {e}")
            traceback.print_exc()
            
        print("\n" + "=" * 50)
        print("🎯 DIAGNOSTIC COMPLETE")
        
    except Exception as e:
        print(f"💥 CRITICAL ERROR: {e}")
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_balance_diagnostics())
