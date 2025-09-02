#!/usr/bin/env python

import os
import time
from decimal import Decimal
from typing import Dict, List, Optional, Tuple

from pydantic import Field, SecretStr

from hummingbot.client.config.config_data_types import BaseConnectorConfigMap
from hummingbot.connector.exchange.standard import standard_constants as CONSTANTS
from hummingbot.connector.exchange.standard.standard_constants import get_token_addresses, TOKEN_DECIMALS, DEFAULT_DOMAIN
from hummingbot.core.utils.async_utils import safe_ensure_future

# Load environment variables from .env file
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # python-dotenv not installed, skip

# Required constants for connector registration
CENTRALIZED = True  # Standard Testnet is a centralized exchange (CLOB)
USE_ETHEREUM_WALLET = False  # Set to False so it appears in balance command  
EXAMPLE_PAIR = "SOMI-USDC" if DEFAULT_DOMAIN == "mainnet" else "STT-USDC"
DEFAULT_FEES = [0.1, 0.1]  # [maker_fee_percent, taker_fee_percent]
USE_ETH_GAS_LOOKUP = False  # Uses its own gas estimation


def get_default_private_key():
    """Get private key from environment variable or prompt."""
    return os.getenv("SOMNIA_PRIVATE_KEY", "")


def get_default_wallet_address():
    """Get wallet address from environment variable or prompt."""
    return os.getenv("SOMNIA_WALLET_ADDRESS", "")


class StandardConfigMap(BaseConnectorConfigMap):
    """
    Configuration map for Somnia exchange connector.
    """
    connector: str = "standard"
    somnia_private_key: SecretStr = Field(
        default_factory=get_default_private_key,
        json_schema_extra={
            "prompt": "Enter your Somnia wallet private key (or set SOMNIA_PRIVATE_KEY env var)",
            "is_secure": True,
            "is_connect_key": True,
            "prompt_on_new": True,
        }
    )
    somnia_wallet_address: str = Field(
        default_factory=get_default_wallet_address,
        json_schema_extra={
            "prompt": "Enter your Somnia wallet address (or set SOMNIA_WALLET_ADDRESS env var)",
            "is_connect_key": True,
            "prompt_on_new": True,
        }
    )


# Set KEYS for connector registration
KEYS = StandardConfigMap.construct()


def split_trading_pair(trading_pair: str) -> Tuple[str, str]:
    """
    Split a trading pair into base and quote assets.
    
    Args:
        trading_pair: Trading pair in format "BASE-QUOTE"
        
    Returns:
        Tuple of (base, quote) asset symbols
    """
    try:
        base, quote = trading_pair.split("-")
        return base.strip(), quote.strip()
    except ValueError:
        raise ValueError(f"Invalid trading pair format: {trading_pair}")


def convert_symbol_to_address(symbol: str, domain: str = DEFAULT_DOMAIN) -> Optional[str]:
    """
    Convert token symbol to contract address.
    
    Args:
        symbol: Token symbol (e.g., "STT", "USDC")
        domain: Network domain ("mainnet" or "testnet")
        
    Returns:
        Contract address or None if not found
    """
    token_addresses = get_token_addresses(domain)
    return token_addresses.get(symbol.upper())


def convert_address_to_symbol(address: str, domain: str = DEFAULT_DOMAIN) -> Optional[str]:
    """
    Convert contract address to token symbol.
    
    Args:
        address: Contract address
        domain: Network domain ("mainnet" or "testnet")
        
    Returns:
        Token symbol or None if not found
    """
    address = address.lower()
    token_addresses = get_token_addresses(domain)
    for symbol, addr in token_addresses.items():
        if addr.lower() == address:
            return symbol
    return None


def get_token_decimals(symbol: str) -> int:
    """
    Get number of decimals for a token.
    
    Args:
        symbol: Token symbol
        
    Returns:
        Number of decimals (defaults to 18 if not found)
    """
    return TOKEN_DECIMALS.get(symbol.upper(), 18)


def convert_to_exchange_trading_pair(hb_trading_pair: str) -> str:
    """
    Convert Hummingbot trading pair to exchange format.
    
    Args:
        hb_trading_pair: Hummingbot trading pair format (e.g., "STT-USDC")
        
    Returns:
        Exchange trading pair format (e.g., "STTUSDC")
    """
    # Remove the dash to get exchange format
    return hb_trading_pair.replace("-", "").upper()


def convert_from_exchange_trading_pair(exchange_trading_pair: str) -> str:
    """
    Convert exchange trading pair to Hummingbot format.
    
    Args:
        exchange_trading_pair: Exchange trading pair format (e.g., "STTUSDC")
        
    Returns:
        Hummingbot trading pair format (e.g., "STT-USDC")
    """
    # Convert STTUSDC -> STT-USDC by finding the base/quote split
    pair = exchange_trading_pair.upper()
    
    # Known token symbols to help with splitting
    known_tokens = list(CONSTANTS.TOKEN_ADDRESSES_PER_DOMAIN["mainnet"].keys()) + list(CONSTANTS.TOKEN_ADDRESSES_PER_DOMAIN["testnet"].keys())
    known_tokens = list(set(known_tokens))  # Remove duplicates
    
    # Try to find a match where the pair starts with a known token
    for token in known_tokens:
        if pair.startswith(token):
            base = token
            quote = pair[len(token):]
            if quote in known_tokens:
                return f"{base}-{quote}"
    
    # Fallback: assume the last 4 characters are USDC (most common quote)
    if len(pair) > 4 and pair.endswith("USDC"):
        base = pair[:-4]
        return f"{base}-USDC"
    
    # If we can't parse it, return as-is (this shouldn't happen in normal operation)
    return exchange_trading_pair


def convert_to_exchange_symbol(hb_symbol: str) -> str:
    """
    Convert Hummingbot symbol to exchange symbol format.
    
    Args:
        hb_symbol: Hummingbot symbol
        
    Returns:
        Exchange symbol format
    """
    return hb_symbol.upper()


def convert_from_exchange_symbol(exchange_symbol: str) -> str:
    """
    Convert exchange symbol to Hummingbot format.
    
    Args:
        exchange_symbol: Exchange symbol
        
    Returns:
        Hummingbot symbol format
    """
    return exchange_symbol.upper()


def get_trading_pair_from_symbols(base: str, quote: str) -> str:
    """
    Construct trading pair from base and quote symbols.
    
    Args:
        base: Base asset symbol
        quote: Quote asset symbol
        
    Returns:
        Trading pair in format "BASE-QUOTE"
    """
    return f"{base.upper()}-{quote.upper()}"


def calculate_mid_price(bids: List[Dict], asks: List[Dict]) -> Optional[Decimal]:
    """
    Calculate mid price from order book data.
    
    Args:
        bids: List of bid orders with 'price' key
        asks: List of ask orders with 'price' key
        
    Returns:
        Mid price or None if cannot calculate
    """
    try:
        if not bids or not asks:
            return None
            
        best_bid = max(bids, key=lambda x: Decimal(str(x['price'])))
        best_ask = min(asks, key=lambda x: Decimal(str(x['price'])))
        
        bid_price = Decimal(str(best_bid['price']))
        ask_price = Decimal(str(best_ask['price']))
        
        return (bid_price + ask_price) / Decimal("2")
        
    except Exception:
        return None


def normalize_trading_pair(trading_pair: str) -> str:
    """
    Normalize trading pair format.
    
    Args:
        trading_pair: Trading pair
        
    Returns:
        Normalized trading pair
    """
    return trading_pair.upper().replace("/", "-").replace("_", "-")


def generate_timestamp() -> float:
    """
    Generate current timestamp.
    
    Returns:
        Current timestamp in seconds
    """
    return time.time()


def generate_order_id() -> str:
    """
    Generate a unique order ID.
    
    Returns:
        Unique order ID string
    """
    return f"somnia_{int(time.time() * 1000000)}"


def validate_trading_pair(trading_pair: str) -> bool:
    """
    Validate if trading pair is supported.
    
    Args:
        trading_pair: Trading pair to validate
        
    Returns:
        True if valid, False otherwise
    """
    try:
        base, quote = split_trading_pair(trading_pair)
        base_address = convert_symbol_to_address(base)
        quote_address = convert_symbol_to_address(quote)
        return base_address is not None and quote_address is not None
    except Exception:
        return False


def format_amount(amount: Decimal, decimals: int) -> str:
    """
    Format amount for blockchain transaction.
    
    Args:
        amount: Amount to format
        decimals: Token decimals
        
    Returns:
        Formatted amount string
    """
    multiplier = Decimal(10) ** decimals
    wei_amount = int(amount * multiplier)
    return str(wei_amount)


def parse_amount(amount_str: str, decimals: int) -> Decimal:
    """
    Parse amount from blockchain format.
    
    Args:
        amount_str: Amount string from blockchain
        decimals: Token decimals
        
    Returns:
        Parsed decimal amount
    """
    wei_amount = Decimal(str(amount_str))
    divisor = Decimal(10) ** decimals
    return wei_amount / divisor


def build_standard_web3_config() -> Dict:
    """
    Build configuration for StandardWeb3 client.
    
    Returns:
        Configuration dictionary
    """
    domain = os.getenv("SOMNIA_DOMAIN", DEFAULT_DOMAIN)
    from .standard_constants import DOMAIN_CONFIG
    
    config = DOMAIN_CONFIG[domain]
    
    return {
        "chain_id": config["chain_id"],
        "rpc_url": config["rpc_url"],
        "exchange_address": config["standard_exchange_address"],
        "api_url": config["standard_api_url"],
        "websocket_url": config["standard_websocket_url"],
    }
