import argparse
import logging
from concurrent.futures import ThreadPoolExecutor
import yaml
from dotenv import load_dotenv
import os
from typing import Dict
from kalshi_python import Configuration, KalshiClient
from cryptography.hazmat.primitives import serialization
from mm import AvellanedaMarketMaker

def load_config(config_file):
    with open(config_file, 'r') as f:
        return yaml.safe_load(f)

class KalshiMMAdapter:
    """
    Minimal shim over kalshi_python.KalshiClient so mm.py does not need changes.
    """
    def __init__(self, sdk_client, market_ticker, trade_side, logger):
        self.client = sdk_client
        self.market_ticker = market_ticker
        self.logger = logger
        self.trade_side = trade_side  # for logging; no behavior

    def get_price(self):
        # SDK returns a Pydantic model; access fields accordingly
        m = self.client.get_market(self.market_ticker)
        # Some SDKs expose m.market.yes_bid (cents) etc.
        market = m.market
        def c2d(x): return None if x is None else round(x / 100.0, 2)
        yes_bid, yes_ask = c2d(market.yes_bid), c2d(market.yes_ask)
        no_bid,  no_ask  = c2d(market.no_bid),  c2d(market.no_ask)
        yes_mid = round((yes_bid + yes_ask)/2, 2) if yes_bid is not None and yes_ask is not None else None
        no_mid  = round((no_bid  + no_ask)/2, 2)  if no_bid  is not None and no_ask  is not None else None
        return {
            "yes": yes_mid,
            "no":  no_mid,
            "quotes": {
                "yes": {"bid": yes_bid, "ask": yes_ask},
                "no":  {"bid":  no_bid, "ask":  no_ask},
            },
        }
    def get_orders(self):
        """
        Return current resting orders for this market's ticker.
        Works with kalshi_python Pydantic models and dict responses.
        """
        resp = self.client.get_orders(ticker=self.market_ticker, status="resting")  # SDK call

        # Prefer Pydantic attribute access (SDK)
        orders = getattr(resp, "orders", None)
        if orders is None:
            # Defensive fallback in case a dict-like response is ever returned
            try:
                orders = resp["orders"]
            except Exception:
                orders = []

        # If mm.py expects dicts, normalize here; otherwise you can return models.
        norm = []
        for o in orders:
            # Pydantic model attribute access (with safe fallbacks)
            order_id = getattr(o, "order_id", None) or (o.get("order_id") if isinstance(o, dict) else None)
            side     = getattr(o, "side", None)     or (o.get("side")     if isinstance(o, dict) else None)
            action   = getattr(o, "action", None)   or (o.get("action")   if isinstance(o, dict) else None)
            yes_px   = getattr(o, "yes_price", None) or (o.get("yes_price") if isinstance(o, dict) else None)
            no_px    = getattr(o, "no_price", None)  or (o.get("no_price")  if isinstance(o, dict) else None)
            count    = getattr(o, "count", None)     or (o.get("count")     if isinstance(o, dict) else None)

            norm.append({
                "order_id": order_id,
                "side": side,           # "yes"/"no"
                "action": action,       # "buy"/"sell"
                "yes_price": yes_px,    # cents or None
                "no_price": no_px,      # cents or None
                "count": count,
            })
        return norm

    def get_position(self):
        """
        Return net position (int) for this market's ticker.
        kalshi_python returns a Pydantic model; do not use dict .get().
        """
        pos = 0
        resp = self.client.get_positions(ticker=self.market_ticker)  # model: GetPositionsResponse

        # Prefer model attributes; only fallback to dict if necessary
        positions = getattr(resp, "positions", None)
        if positions is None:
            # very defensive fallback
            try:
                positions = resp["positions"]
            except Exception:
                positions = []

        for p in positions:
            # p is also a model (Position); prefer attributes
            ticker = getattr(p, "ticker", None)
            if ticker != self.market_ticker:
                continue

            # Skip settled if the field exists (SDKs differ)
            settled = getattr(p, "settled", None)
            if settled is True:
                continue
            settlement_status = getattr(p, "settlement_status", None)
            if isinstance(settlement_status, str) and settlement_status.lower() == "settled":
                continue

            amount = getattr(p, "position", 0)
            try:
                pos += int(amount)
            except Exception:
                pos += int(float(amount or 0))
        return pos


    def place_order(self, action, side, price, quantity, expiration_ts=None):
        cents = int(round(price * 100))
        res = self.client.create_order(
            ticker=self.market_ticker,
            action=action,    # "buy" / "sell"
            side=side,        # "yes" / "no"
            price=cents,
            count=int(quantity),
            expiration_ts=expiration_ts,
        )
        # SDK may return model with .order_id
        return getattr(res, "order_id", None) or res.get("order_id")

    def cancel_order(self, order_id):
        self.client.cancel_order(order_id)
        return True

    def logout(self):
        pass  

def create_api(api_cfg, logger):
    """
    Create an authenticated Kalshi client using the official SDK.
    Reads API key + RSA private key from environment variables.
    """
    env = os.getenv("KALSHI_ENV", "DEMO").upper()
    base_url = os.getenv("KALSHI_BASE_URL")
    api_key_id = os.getenv("KALSHI_API_KEY_ID")
    private_key_path = os.getenv("KALSHI_RSA_PRIVATE_KEY_PATH")


    if not (api_key_id and private_key_path and base_url):
        raise ValueError("Missing Kalshi credentials or base URL in .env")

    # Configure SDK
    config = Configuration(host=base_url)
    with open(private_key_path, "r") as f:
        config.private_key_pem = f.read()
    config.api_key_id = api_key_id

    sdk = KalshiClient(config)
    logger.info(f"Connected to Kalshi ({env}) via {base_url}")

    trade_side = api_cfg.get("trade_side", "yes")
    return KalshiMMAdapter(sdk, api_cfg["market_ticker"], trade_side, logger)


def create_market_maker(mm_config, api, logger):
    return AvellanedaMarketMaker(
        logger=logger,
        api=api,
        gamma=mm_config.get('gamma', 0.1),
        k=mm_config.get('k', 1.5),
        sigma=mm_config.get('sigma', 0.5),
        T=mm_config.get('T', 3600),
        max_position=mm_config.get('max_position', 100),
        order_expiration=mm_config.get('order_expiration', 300),
        min_spread=mm_config.get('min_spread', 0.01),
        position_limit_buffer=mm_config.get('position_limit_buffer', 0.1),
        inventory_skew_factor=mm_config.get('inventory_skew_factor', 0.01),
        trade_side = api.trade_side
    )
def run_strategy(config_name: str, config: Dict):
    logger = logging.getLogger(f"Strategy_{config_name}")
    logger.setLevel(config.get('log_level', 'INFO'))

    fh = logging.FileHandler(f"{config_name}.log")
    fh.setLevel(config.get('log_level', 'INFO'))
    ch = logging.StreamHandler()
    ch.setLevel(config.get('log_level', 'INFO'))

    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    fh.setFormatter(formatter)
    ch.setFormatter(formatter)
    logger.addHandler(fh)
    logger.addHandler(ch)

    logger.info(f"Starting strategy: {config_name}")

    api = None
    try:
        # Create API
        api = create_api(config['api'], logger)

        # Create market maker
        market_maker = create_market_maker(config['market_maker'], api, logger)
        logger.info(
            f"Pre-run params: side={api.trade_side}, T={market_maker.T}, dt={config.get('dt', 1.0)}, "
            f"gamma={market_maker.gamma}, k={market_maker.k}, sigma={market_maker.sigma}"
        )

        # Run market maker loop
        market_maker.run(config.get('dt', 1.0))

    except KeyboardInterrupt:
        logger.info("Market maker stopped by user")
    except Exception:
        logger.exception("An error occurred")  # full traceback
    finally:
        # Ensure logout happens only if api was created successfully
        try:
            if hasattr(api, "logout"):
                api.logout()
        except Exception:
            logger.exception("Logout failed")





if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Kalshi Market Making Algorithm")
    parser.add_argument("--config", type=str, default="config.yaml", help="Path to config file")
    args = parser.parse_args()

    # Load all configurations
    configs = load_config(args.config)

    # Load environment variables
    load_dotenv()

    # Print the name of every strategy being run
    print("Starting the following strategies:")
    for config_name in configs:
        print(f"- {config_name}")
    
    # Run all strategies in parallel using ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=len(configs)) as executor:
        for config_name, config in configs.items():
            executor.submit(run_strategy, config_name, config)