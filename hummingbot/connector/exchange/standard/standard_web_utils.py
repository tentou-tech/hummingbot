#!/usr/bin/env python

import time
from typing import Optional

import aiohttp

import hummingbot.connector.exchange.standard.standard_constants as CONSTANTS
from hummingbot.core.api_throttler.async_throttler import AsyncThrottler
from hummingbot.core.api_throttler.data_types import LinkedLimitWeightPair, RateLimit
from hummingbot.core.web_assistant.auth import AuthBase
from hummingbot.core.web_assistant.web_assistants_factory import WebAssistantsFactory


# Rate limits for Somnia API
RATE_LIMITS = [
    RateLimit(
        limit_id="general",
        limit=CONSTANTS.MAX_REQUESTS_PER_SECOND,
        time_interval=1.0
    ),
    RateLimit(
        limit_id="orderbook",
        limit=20,
        time_interval=1.0
    ),
    RateLimit(
        limit_id=CONSTANTS.GET_ORDERBOOK_PATH_URL,
        limit=20,
        time_interval=1.0
    ),
    RateLimit(
        limit_id="trades",
        limit=20,
        time_interval=1.0
    ),
    RateLimit(
        limit_id="orders",
        limit=10,
        time_interval=1.0
    ),
    RateLimit(
        limit_id=CONSTANTS.GET_ACCOUNT_ORDERS_PATH_URL,
        limit=10,
        time_interval=1.0
    ),
    RateLimit(
        limit_id=CONSTANTS.GET_ACCOUNT_TRADES_PATH_URL,
        limit=10,
        time_interval=1.0
    ),
]


def public_rest_url(path_url: str, domain: str = CONSTANTS.DEFAULT_DOMAIN, **kwargs) -> str:
    """
    Creates a full URL for provided public REST endpoint.
    
    Args:
        path_url: A public REST endpoint or endpoint key
        domain: The Somnia domain to connect to
        **kwargs: Additional parameters for URL formatting
        
    Returns:
        The full URL to the endpoint
    """
    if path_url.startswith("http"):
        return path_url
    
    # Get the base URL for the specified domain
    base_url = CONSTANTS.DOMAIN_CONFIG[domain]["api_url"].rstrip('/')
    
    # Check if path_url is a key in REST_API_ENDPOINTS
    if hasattr(CONSTANTS, 'REST_API_ENDPOINTS') and path_url in CONSTANTS.REST_API_ENDPOINTS:
        endpoint_template = CONSTANTS.REST_API_ENDPOINTS[path_url]
        # Format the template with provided kwargs
        formatted_endpoint = endpoint_template.format(**kwargs)
        return base_url + formatted_endpoint
    
    # For GraphQL endpoints (legacy support)
    if "graphql" in path_url.lower():
        return base_url + "/graphql"
    
    # For other API endpoints - ensure proper URL joining with /
    path = path_url.lstrip('/')
    
    # If it's a throttler ID (like GET_ORDERBOOK), convert to actual API path
    if path_url == "GET_ORDERBOOK":
        return f"{base_url}/api/orderbook"
    elif path_url in ["GET_ACCOUNT_INFO", "GET_ACCOUNT_PATH_URL"]:
        return f"{base_url}/api/account"
    elif path_url == "GET_TOKEN_INFO":
        return f"{base_url}/api/token"
    elif path_url == "GET_PAIRS":
        return f"{base_url}/api/pairs"
    elif path_url == "POST_ORDER":
        return f"{base_url}/api/orders"
    elif path_url == "DELETE_ORDER":
        return f"{base_url}/api/orders"
    else:
        # For actual path URLs, use proper / separation
        return f"{base_url}/{path}"


def private_rest_url(path_url: str, domain: str = CONSTANTS.DEFAULT_DOMAIN) -> str:
    """
    Creates a full URL for provided private REST endpoint.
    
    Args:
        path_url: A private REST endpoint
        domain: The domain to connect to
        
    Returns:
        The full URL to the endpoint
    """
    return public_rest_url(path_url=path_url, domain=domain)


def build_api_factory(
    throttler: Optional[AsyncThrottler] = None,
    auth: Optional[AuthBase] = None,
) -> WebAssistantsFactory:
    """
    Build web assistants factory for Somnia API.
    
    Args:
        throttler: Rate limiter
        auth: Authentication handler
        
    Returns:
        WebAssistantsFactory instance
    """
    throttler = throttler or create_throttler()
    api_factory = WebAssistantsFactory(throttler=throttler, auth=auth)
    return api_factory


def create_throttler() -> AsyncThrottler:
    """
    Create rate limiter for Somnia API.
    
    Returns:
        AsyncThrottler instance
    """
    return AsyncThrottler(RATE_LIMITS)


async def get_current_server_time(
    throttler: AsyncThrottler, 
    domain: str = CONSTANTS.DEFAULT_DOMAIN
) -> float:
    """
    Get current server time.
    
    Args:
        throttler: Rate limiter
        domain: Domain to connect to
        
    Returns:
        Current server timestamp
    """
    # For now, return local time since Somnia doesn't have a dedicated time endpoint
    # In a real implementation, you might query the blockchain for the latest block timestamp
    return float(time.time())


def build_graphql_request(query: str, variables: dict = None) -> dict:
    """
    Build GraphQL request payload.
    
    Args:
        query: GraphQL query string
        variables: Query variables
        
    Returns:
        Request payload dictionary
    """
    payload = {"query": query}
    if variables:
        payload["variables"] = variables
    return payload


def get_websocket_url(domain: str = CONSTANTS.DEFAULT_DOMAIN) -> str:
    """
    Get WebSocket URL for real-time data.
    
    Args:
        domain: Domain to connect to
        
    Returns:
        WebSocket URL
    """
    return CONSTANTS.DOMAIN_CONFIG[domain]["websocket_url"]


def format_trading_pair_for_api(trading_pair: str) -> tuple:
    """
    Format trading pair for API calls.
    
    Args:
        trading_pair: Trading pair in Hummingbot format
        
    Returns:
        Tuple of (base_symbol, quote_symbol)
    """
    from .standard_utils import split_trading_pair, convert_symbol_to_address
    
    base, quote = split_trading_pair(trading_pair)
    
    # Convert to addresses for API calls
    base_address = convert_symbol_to_address(base)
    quote_address = convert_symbol_to_address(quote)
    
    return base_address, quote_address
