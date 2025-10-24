# Imports
from kalshi_python import Configuration, KalshiClient
from kalshi_python.models.create_order_request import CreateOrderRequest
import kalshi_python
from dotenv import load_dotenv
import os
import requests 
import time
import uuid
import kalshi_python
from kalshi_python.models.create_order_request import CreateOrderRequest
from kalshi_python.models.create_order_response import CreateOrderResponse
from kalshi_python.rest import ApiException
from pprint import pprint

LIMIT=10000


configuration = kalshi_python.Configuration(
    host = "https://api.elections.kalshi.com/trade-api/v2"
)
load_dotenv()
env = os.getenv("KALSHI_ENV", "DEMO").upper()
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

path = "/Users/archan/kalshimarketmaker/markets.txt"

KEYWORDS = ["trump", "democratic", "election", "inflation"]  # edit as you like

def fetch_all_tickers():
    markets = client.get_markets(limit=LIMIT).markets
    tickers = [
        market.ticker
        for market in markets
        if any(kw.lower() in market.title.lower() for kw in KEYWORDS) 
    ]
    return tickers


def write_tickers(tickers):
    with open("markets.txt", "w") as f:
        for t in tickers:
            f.write(t + "\n")
    print(f"Wrote {len(tickers)} tickers to markets.txt")


def main():
    tickers = fetch_all_tickers()
    write_tickers(tickers)

if __name__ == "__main__":
    main()
