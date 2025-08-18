#!/usr/bin/env python

"""
Somnia API Wrapper - Fixes standardweb3 library compatibility issues

This module provides a wrapper around standardweb3 API calls to fix the format
mismatch between what standardweb3 sends vs what Somnia testnet API expects.

The main issues fixed:
1. standardweb3 sends: base=0x...&quote=0x...
2. Somnia API expects: ticker_id=SOL_USDC

This wrapper intercepts API calls and transforms them to the correct format.
"""

import logging
from typing import Any, Dict

import aiohttp


class SomniaAPIWrapper:
    """
    API wrapper that fixes standardweb3 compatibility issues with Somnia testnet
    """

    def __init__(self, api_url: str):
        self.api_url = api_url.rstrip('/')
        self.logger = logging.getLogger(__name__)

        # Token address to symbol mapping for Somnia testnet
        self.token_address_to_symbol = {
            '0xb35a7935F8fbc52fB525F16Af09329b3794E8C42': 'SOL',
            '0x0ED782B8079529f7385c3eDA9fAf1EaA0DbC6a17': 'USDC',
        }

        # Reverse mapping for symbol to address
        self.symbol_to_address = {v: k for k, v in self.token_address_to_symbol.items()}

    def _transform_address_to_ticker(self, base_address: str, quote_address: str) -> str:
        """
        Transform token addresses to ticker_id format that Somnia API expects

        Args:
            base_address: Base token contract address
            quote_address: Quote token contract address

        Returns:
            ticker_id in format like 'SOL_USDC'
        """
        base_symbol = self.token_address_to_symbol.get(base_address)
        quote_symbol = self.token_address_to_symbol.get(quote_address)

        if not base_symbol or not quote_symbol:
            self.logger.warning(f"Unknown token addresses: base={base_address}, quote={quote_address}")
            # Fallback to address format if symbols not found
            return f"{base_address}_{quote_address}"

        return f"{base_symbol}_{quote_symbol}"

    def _transform_ticker_to_addresses(self, ticker_id: str) -> tuple[str, str]:
        """
        Transform ticker_id back to token addresses

        Args:
            ticker_id: Ticker in format like 'SOL_USDC' or 'SOL/USDC'

        Returns:
            Tuple of (base_address, quote_address)
        """
        # Handle both underscore and slash formats
        if '_' in ticker_id:
            base_symbol, quote_symbol = ticker_id.split('_', 1)
        elif '/' in ticker_id:
            base_symbol, quote_symbol = ticker_id.split('/', 1)
        else:
            raise ValueError(f"Invalid ticker_id format: {ticker_id}")

        base_address = self.symbol_to_address.get(base_symbol)
        quote_address = self.symbol_to_address.get(quote_symbol)

        if not base_address or not quote_address:
            raise ValueError(f"Unknown symbols in ticker: {base_symbol}, {quote_symbol}")

        return base_address, quote_address

    async def fetch_orderbook(self, base: str, quote: str) -> Dict[str, Any]:
        """
        Fetch orderbook data with proper format transformation

        Args:
            base: Base token address (what standardweb3 sends)
            quote: Quote token address (what standardweb3 sends)

        Returns:
            Orderbook data in standardweb3 expected format
        """
        try:
            # Transform to Somnia API format
            ticker_id = self._transform_address_to_ticker(base, quote)

            # Make the API call with correct format
            url = f"{self.api_url}/api/orderbook"
            params = {'ticker_id': ticker_id}

            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params, timeout=10) as response:
                    if response.status == 200:
                        data = await response.json()

                        # Transform response to standardweb3 expected format
                        # Somnia returns: {"ticker_id": "SOL/USDC", "bids": [...], "asks": [...]}
                        # standardweb3 expects similar format

                        return {
                            'symbol': data.get('ticker_id', ticker_id.replace('_', '/')),
                            'bids': data.get('bids', []),
                            'asks': data.get('asks', []),
                            'timestamp': data.get('timestamp'),
                            # Add additional fields that standardweb3 might expect
                            'base': base,
                            'quote': quote
                        }
                    else:
                        error_text = await response.text()
                        raise Exception(f"HTTP error! status: {response.status}, response: {error_text}")

        except Exception as e:
            self.logger.error(f"Error in fetch_orderbook: {e}")
            raise

    async def fetch_token_info(self, address: str) -> Dict[str, Any]:
        """
        Fetch token information with proper format transformation

        Args:
            address: Token contract address

        Returns:
            Token info in standardweb3 expected format
        """
        try:
            # For now, return known token info since the API endpoint format is unclear
            symbol = self.token_address_to_symbol.get(address)
            if symbol:
                return {
                    'address': address,
                    'symbol': symbol,
                    'name': symbol,  # Simplified
                    'decimals': 18 if symbol != 'USDC' else 6,  # Common decimals
                }
            else:
                # Try to call actual API if it has a working endpoint
                raise Exception(f"Unknown token address: {address}")

        except Exception as e:
            self.logger.error(f"Error in fetch_token_info: {e}")
            raise

    async def fetch_pair_info(self, base: str, quote: str) -> Dict[str, Any]:
        """
        Fetch trading pair information

        Args:
            base: Base token address
            quote: Quote token address

        Returns:
            Pair info in standardweb3 expected format
        """
        try:
            ticker_id = self._transform_address_to_ticker(base, quote)
            base_symbol = self.token_address_to_symbol.get(base, base)
            quote_symbol = self.token_address_to_symbol.get(quote, quote)

            return {
                'base': base,
                'quote': quote,
                'base_symbol': base_symbol,
                'quote_symbol': quote_symbol,
                'ticker_id': ticker_id,
                'active': True
            }

        except Exception as e:
            self.logger.error(f"Error in fetch_pair_info: {e}")
            raise
