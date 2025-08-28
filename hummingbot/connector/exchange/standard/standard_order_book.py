from typing import Any, Dict, Optional

from hummingbot.core.data_type.common import TradeType
from hummingbot.core.data_type.order_book import OrderBook
from hummingbot.core.data_type.order_book_message import OrderBookMessage, OrderBookMessageType


class StandardOrderBook(OrderBook):
    @classmethod
    def snapshot_message_from_exchange_websocket(
        cls, msg: Dict[str, Any], timestamp: float, metadata: Optional[Dict] = None
    ) -> OrderBookMessage:
        """
        Creates a snapshot message with the order book snapshot message
        :param msg: the response from the exchange when requesting the order book snapshot
        :param timestamp: the snapshot timestamp
        :param metadata: a dictionary with extra information to add to the snapshot data
        :return: a snapshot message with the snapshot information received from the exchange
        """
        if metadata:
            msg.update(metadata)
        
        return OrderBookMessage(
            OrderBookMessageType.SNAPSHOT,
            {
                "trading_pair": msg["trading_pair"],
                "update_id": int(timestamp * 1000),  # Use timestamp as update_id
                "bids": msg.get("bids", []),
                "asks": msg.get("asks", []),
            },
            timestamp=timestamp,
        )

    @classmethod
    def snapshot_message_from_exchange_rest(
        cls, msg: Dict[str, Any], timestamp: float, metadata: Optional[Dict] = None
    ) -> OrderBookMessage:
        """
        Creates a snapshot message with the order book snapshot message
        :param msg: the response from the exchange when requesting the order book snapshot
        :param timestamp: the snapshot timestamp
        :param metadata: a dictionary with extra information to add to the snapshot data
        :return: a snapshot message with the snapshot information received from the exchange
        """
        if metadata:
            msg.update(metadata)
            
        return OrderBookMessage(
            OrderBookMessageType.SNAPSHOT,
            {
                "trading_pair": msg["trading_pair"],
                "update_id": int(timestamp * 1000),  # Use timestamp as update_id
                "bids": msg.get("bids", []),
                "asks": msg.get("asks", []),
            },
            timestamp=timestamp,
        )

    @classmethod
    def diff_message_from_exchange(
        cls, msg: Dict[str, Any], timestamp: float, metadata: Optional[Dict] = None
    ) -> OrderBookMessage:
        """
        Creates a diff message with the changes in the order book
        :param msg: the changes received from the exchange
        :param timestamp: the timestamp of the diff
        :param metadata: a dictionary with extra information to add to the diff data
        :return: a diff message with the changes information received from the exchange
        """
        if metadata:
            msg.update(metadata)
            
        return OrderBookMessage(
            OrderBookMessageType.DIFF,
            {
                "trading_pair": msg["trading_pair"],
                "update_id": int(timestamp * 1000),
                "bids": msg.get("bids", []),
                "asks": msg.get("asks", []),
            },
            timestamp=timestamp,
        )

    @classmethod
    def trade_message_from_exchange(
        cls, msg: Dict[str, Any], metadata: Optional[Dict] = None
    ) -> OrderBookMessage:
        """
        Creates a trade message with the information from the trade event sent by the exchange
        :param msg: the trade information received from the exchange
        :param metadata: a dictionary with extra information to add to the trade message
        :return: a trade message with the trade information received from the exchange
        """
        if metadata:
            msg.update(metadata)
            
        trade_type = float(msg["price"]) > 0.0  # Simplified logic - could be enhanced
        
        return OrderBookMessage(
            OrderBookMessageType.TRADE,
            {
                "trading_pair": msg["trading_pair"],
                "trade_type": TradeType.BUY if trade_type else TradeType.SELL,
                "trade_id": msg.get("trade_id", str(int(msg.get("timestamp", 0)))),
                "update_id": int(msg.get("timestamp", 0)),
                "price": str(msg["price"]),
                "amount": str(msg.get("amount") or msg.get("quantity", "0")),
            },
            timestamp=float(msg.get("timestamp", 0)),
        )

    
    @classmethod
    def snapshot_message_from_exchange(
        cls, msg: Dict[str, Any], timestamp: float, metadata: Optional[Dict] = None
    ) -> OrderBookMessage:
        """
        Alias for snapshot_message_from_exchange_rest for test compatibility.
        """
        return cls.snapshot_message_from_exchange_rest(msg, timestamp, metadata)
        
    @classmethod
    def diff_message_from_exchange(
        cls, msg: Dict[str, Any], timestamp: float, metadata: Optional[Dict] = None
    ) -> OrderBookMessage:
        """
        Creates a diff message with the order book update message
        :param msg: the response from the exchange when requesting the order book update
        :param timestamp: the update timestamp
        :param metadata: a dictionary with extra information to add to the update data
        :return: a diff message with the update information received from the exchange
        """
        if metadata:
            msg.update(metadata)
            
        return OrderBookMessage(
            OrderBookMessageType.DIFF,
            {
                "trading_pair": msg["trading_pair"],
                "update_id": int(timestamp * 1000),
                "bids": msg.get("bids", []),
                "asks": msg.get("asks", []),
            },
            timestamp=timestamp,
        )
