import time, sys, os, signal
import argparse
import logging
from concurrent.futures import ThreadPoolExecutor
import yaml
from dotenv import load_dotenv
import os
from typing import Dict
from kalshi_python import Configuration, KalshiClient
from cryptography.hazmat.primitives import serialization
from market_maker import KalshiTradingAPI
import kalshi_python
ONLY_ONCE = True
configuration = kalshi_python.Configuration(
    host = "https://api.elections.kalshi.com/trade-api/v2"
)
load_dotenv()
base_url = os.getenv("KALSHI_BASE_URL")
api_key_id = os.getenv("KALSHI_API_KEY_ID")
private_key_path = os.getenv("KALSHI_RSA_PRIVATE_KEY_PATH")
# Read private key from file
with open(private_key_path, 'r') as f:
    private_key = f.read()

# Configure API key authentication
configuration.api_key_id = api_key_id
configuration.private_key_pem = private_key

# Initialize the Kalshi client
client = kalshi_python.KalshiClient(configuration)


# Makes sure we can stop
STOP = False
def _stop(*_): 
    global STOP; STOP = True
signal.signal(signal.SIGINT, _stop)
signal.signal(signal.SIGTERM, _stop)

# Reads all the tickers in the markets.txt file
def read_tickers(path="markets.txt"):
    with open(path, "r") as f:
        return [ln.strip() for ln in f if ln.strip() and not ln.strip().startswith("#")]


def trade_forever(ticker, sleep_s=1.0):
    api = KalshiTradingAPI(
        market_ticker=ticker,
        base_url=base_url,
        client=client
    )
    print(f"[{ticker}] started.")
    while not STOP:
        api.mm()
        time.sleep(sleep_s)

def main():
    tickers = read_tickers()
    if not tickers:
        print("No tickers in markets.txt"); sys.exit(1)

    print(f"Starting {len(tickers)} market(s). Press Ctrl+C to stop.")
    # simplest round-robin: do one mm() per ticker per loop
    apis = [
        KalshiTradingAPI(market_ticker=t, base_url=base_url, client=client)
        for t in tickers
    ]
    while not STOP:
        for api in apis:
            api.mm()
            if STOP: break
        time.sleep(1.0)

if __name__ == "__main__":
    main()