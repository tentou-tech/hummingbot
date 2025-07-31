#!/usr/bin/env python

import logging
import time
import uuid
from typing import Any, Dict, Tuple

import aiohttp

from hummingbot.core.utils.tracking_nonce import get_tracking_nonce

from .somnia_constants import SOMNIA_GRAPHQL_ENDPOINT

# Global logger for this file
logger = logging.getLogger(__name__)


def get_new_client_order_id(is_buy: bool, trading_pair: str) -> str:
    """
    Creates a client order ID for a new order.

    Args:
        is_buy: True if the order is a buy order, False otherwise
        trading_pair: The trading pair the order is for

    Returns:
        A unique string client order ID
    """
    side = "B" if is_buy else "S"
    # Use tracking nonce that'll guarantee uniqueness
    nonce = get_tracking_nonce()
    client_order_id = f"SOMNIA_{side}_{trading_pair}_{nonce}"
    return client_order_id


def convert_from_exchange_trading_pair(exchange_trading_pair: str) -> str:
    """
    Converts an exchange trading pair (with possibly custom format) to the standard Hummingbot format.

    Args:
        exchange_trading_pair: Trading pair in exchange format

    Returns:
        Trading pair in Hummingbot format (BASE-QUOTE)
    """
    # Somnia uses the BASE_QUOTE format with underscore, convert to BASE-QUOTE
    if "_" in exchange_trading_pair:
        base, quote = exchange_trading_pair.split("_")
        return f"{base}-{quote}"
    return exchange_trading_pair


def convert_to_exchange_trading_pair(hb_trading_pair: str) -> str:
    """
    Converts a Hummingbot trading pair to the exchange trading pair format.

    Args:
        hb_trading_pair: Trading pair in Hummingbot format (BASE-QUOTE)

    Returns:
        Trading pair in exchange format
    """
    # Convert from BASE-QUOTE to BASE_QUOTE
    base, quote = hb_trading_pair.split("-")
    return f"{base}_{quote}"


def split_trading_pair(trading_pair: str) -> Tuple[str, str]:
    """
    Splits a trading pair string into base and quote asset strings.

    Args:
        trading_pair: The trading pair in Hummingbot format (BASE-QUOTE)

    Returns:
        A tuple of (base_asset, quote_asset)
    """
    base, quote = trading_pair.split("-")
    return base, quote


async def execute_graphql_query(query: str, variables: Dict[str, Any]) -> Dict[str, Any]:
    """
    Executes a GraphQL query against the Somnia API.

    Args:
        query: The GraphQL query string
        variables: Variables to be passed with the query

    Returns:
        The response JSON as a dictionary
    """
    async with aiohttp.ClientSession() as client:
        payload = {
            "query": query,
            "variables": variables
        }

        try:
            async with client.post(
                SOMNIA_GRAPHQL_ENDPOINT,
                json=payload,
                headers={"Content-Type": "application/json"}
            ) as response:
                if response.status != 200:
                    error_response = await response.text()
                    logger.error(f"GraphQL query failed with status {response.status}: {error_response}")
                    raise IOError(f"GraphQL query failed with status {response.status}: {error_response}")

                result = await response.json()

                if "errors" in result:
                    logger.error(f"GraphQL query returned errors: {result['errors']}")
                    raise IOError(f"GraphQL query returned errors: {result['errors']}")

                return result
        except aiohttp.ClientError as e:
            logger.error(f"Error connecting to GraphQL API: {e}")
            raise


def generate_timestamp() -> int:
    """
    Generates a timestamp in milliseconds.

    Returns:
        Current timestamp in milliseconds
    """
    return int(time.time() * 1000)


def generate_uuid() -> str:
    """
    Generates a random UUID.

    Returns:
        A random UUID string
    """
    return str(uuid.uuid4())
