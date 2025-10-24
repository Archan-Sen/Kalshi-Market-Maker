import abc
import time
from typing import Dict, List, Tuple
import requests
import logging
import uuid
import math
from dataclasses import dataclass
from typing import Optional, Literal, Protocol, Dict, Any
import logging
import time
import numpy as np

class KalshiTradingAPI():
    def __init__(
        self,
        market_ticker: str,
        base_url: str,
        client
    ):
        self.market_ticker = market_ticker
        self.base_url = base_url
        self.client = client
    
    # Gets info about the market
    def get_info(self):
        ticker = self.market_ticker 
        api_response = self.client.get_market(ticker).market
        return {
            'yes_bid': api_response.yes_bid, 'yes_ask': api_response.yes_ask,
            'no_bid': api_response.no_bid, 'no_ask': api_response.no_ask,
            'last_price': api_response.last_price
        }

    # Submits the orders    
    def make_order(self, action: str, count: int, side: str, yes_price: Optional[int]=None, expiration_ts: Optional[int]=None, 
                   no_price: Optional[int]=None, post_only: bool=True, cancel_order_on_pause=True, type='limit'):
        order_kwargs = dict(
            action=action,
            count=count,
            side=side,
            ticker=self.market_ticker,
            post_only=post_only,
            cancel_order_on_pause=cancel_order_on_pause,
            type=type,
        )

        # Add optional args only if they’re not None
        if yes_price is not None:
            order_kwargs["yes_price"] = yes_price
        if no_price is not None:
            order_kwargs["no_price"] = no_price
        if expiration_ts is not None:
            order_kwargs["expiration_ts"] = expiration_ts

        # Send the API request
        api_response = self.client.create_order(**order_kwargs)
        return api_response
    
    # Cancel Order 
    def cancel_order(self, order_id):
        api_response = self.client.cancel_order(order_id)
        return api_response

    # Get position 
    def get_position(self):
        api_response = self.client.get_orders(ticker=self.market_ticker)
        return api_response
    
    
    # For markets where there's a profitable spread, penny out everyone else
    def mm(self):
        info = self.get_info()
        yes_bid = info['yes_bid']
        no_bid = info['no_bid']
        if yes_bid + no_bid + 2 < 100:
            self.make_order(action='buy', count=1, side='yes', yes_price=yes_bid + 1)
            self.make_order(action='buy', count=1, side='no', no_price=no_bid + 1)
