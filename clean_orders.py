#!/usr/bin/env python3

"""
Fast Cancel All Orders Script - Uses API instead of contract scanning

Just cancels all your active orders. Super fast with API calls.
"""

import asyncio
import json
import os
import requests
from dotenv import load_dotenv
from web3 import Web3

# Hardcoded configuration
API_BASE_URL = "https://api-somi.standardweb3.com"
RPC_URL = "https://api.infra.mainnet.somnia.network"
CONTRACT_ADDRESS = "0x3Cb2CBb0CeB96c9456b11DbC7ab73c4848F9a14c"
ABI_FILE = "hummingbot/connector/exchange/standard/lib/matching_engine_abi.json"


async def main():
    """Main function - super fast!"""
    
    # Load your wallet info from .env
    load_dotenv()
    private_key = os.getenv("SOMNIA_PRIVATE_KEY")
    wallet_address = os.getenv("SOMNIA_WALLET_ADDRESS")
    
    if not private_key or not wallet_address:
        print("❌ Set SOMNIA_PRIVATE_KEY and SOMNIA_WALLET_ADDRESS in .env file!")
        return
    
    # Connect to blockchain
    w3 = Web3(Web3.HTTPProvider(RPC_URL))
    if not w3.is_connected():
        print(f"❌ Can't connect to {RPC_URL}")
        return
    
    # Load contract
    with open(ABI_FILE, "r") as f:
        abi = json.load(f)
    
    contract = w3.eth.contract(address=CONTRACT_ADDRESS, abi=abi)
    
    print(f"🔍 Getting your active orders from API...")
    print(f"👤 Wallet: {wallet_address}")
    print(f"💰 Balance: {w3.from_wei(w3.eth.get_balance(wallet_address), 'ether')} SOMI")
    print()
    
    # Get all active orders from API - MUCH FASTER!
    try:
        api_url = f"{API_BASE_URL}/api/orders/{wallet_address}/1000/1"
        print(f"🌐 Calling API: {api_url}")
        
        response = requests.get(api_url, timeout=30)
        response.raise_for_status()
        
        data = response.json()
        active_orders = data.get("orders", [])
        total_count = data.get("totalCount", 0)
        
        print(f"📊 API Response: {total_count} total orders found")
        
    except Exception as e:
        print(f"❌ API Error: {e}")
        print("🔄 Falling back to contract scanning...")
        return
    
    if not active_orders:
        print("📭 No active orders found!")
        return
    
    print(f"🎯 Found {len(active_orders)} active orders. Cancelling in batches of 10...")
    
    # Process orders in batches of 10
    success = 0
    failed = 0
    batch_size = 10
    
    for batch_start in range(0, len(active_orders), batch_size):
        batch_end = min(batch_start + batch_size, len(active_orders))
        batch_orders = active_orders[batch_start:batch_end]
        
        print(f"\n📦 Processing batch {batch_start//batch_size + 1}: orders {batch_start + 1}-{batch_end}")
        
        # Prepare batch data for cancelOrders (array of tuples)
        cancel_order_data = []
        
        for order in batch_orders:
            order_id = order.get("orderId") or order.get("id")
            base_addr = order.get("baseToken") or order.get("base")
            quote_addr = order.get("quoteToken") or order.get("quote")
            is_buy = order.get("isBuy") or order.get("side") == "buy"
            
            # Create tuple for this order
            cancel_order_data.append((
                Web3.to_checksum_address(base_addr),
                Web3.to_checksum_address(quote_addr),
                is_buy,
                order_id
            ))
            
            pair = f"{order.get('baseSymbol', 'BASE')}-{order.get('quoteSymbol', 'QUOTE')}"
            side = "BUY" if is_buy else "SELL"
            print(f"  • {side} {pair} #{order_id}")
        
        try:
            print(f"🔨 Batch cancelling {len(batch_orders)} orders...")
            
            # Build batch cancel transaction
            tx = contract.functions.cancelOrders(
                cancel_order_data
            ).build_transaction({
                'from': wallet_address,
                'nonce': w3.eth.get_transaction_count(wallet_address),
                'gas': 3000000,  # Increased gas limit
                'gasPrice': w3.eth.gas_price
            })
            
            # Sign and send
            signed = w3.eth.account.sign_transaction(tx, private_key)
            tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
            
            print(f"⏳ Waiting for confirmation: {tx_hash.hex()}")
            
            # Wait for confirmation
            receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)
            
            if receipt.status == 1:
                print(f"    ✅ Batch cancelled! Gas used: {receipt.gasUsed}")
                success += len(batch_orders)
            else:
                print(f"    ❌ Batch failed")
                failed += len(batch_orders)
                
        except Exception as e:
            print(f"    ❌ Batch Error: {e}")
            failed += len(batch_orders)
        
        # Small delay between batches
        await asyncio.sleep(2)
    
    print(f"\n📊 Done!")
    print(f"  ✅ Cancelled: {success}")
    print(f"  ❌ Failed: {failed}")


if __name__ == "__main__":
    asyncio.run(main())
