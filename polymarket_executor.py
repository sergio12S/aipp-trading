import os
import sys
import json
import argparse
from dotenv import load_dotenv
from py_clob_client_v2.client import ClobClient
from py_clob_client_v2.clob_types import ApiCreds, OrderArgsV2 as OrderArgs
from py_clob_client_v2.constants import POLYGON

# Load default.env
dotenv_path = os.path.join(os.path.dirname(__file__), "default.env")
if os.path.exists(dotenv_path):
    load_dotenv(dotenv_path)
else:
    load_dotenv()

def get_client():
    # Read variables
    api_key = os.getenv("POLYMARKET_API_KEY")
    secret = os.getenv("POLYMARKET_SECRET")
    passphrase = os.getenv("POLYMARKET_PASSPHRASE")
    pk = os.getenv("POLYMARKET_PK")
    funder = os.getenv("POLYMARKET_FUNDER")
    
    # Parse signature type (default to 2 for smart contract/funder)
    sig_type_env = os.getenv("POLYMARKET_SIGNATURE_TYPE")
    sig_type = int(sig_type_env) if sig_type_env else 2
    
    if not (api_key and secret and passphrase and pk):
        raise ValueError("Missing required POLYMARKET_* credentials in default.env / environment")
        
    creds = ApiCreds(
        api_key=api_key,
        api_secret=secret,
        api_passphrase=passphrase
    )
    
    client = ClobClient(
        host="https://clob.polymarket.com",
        chain_id=POLYGON,
        key=pk,
        creds=creds,
        signature_type=sig_type,
        funder=funder
    )
    return client

def test_connection():
    try:
        from py_clob_client_v2.clob_types import BalanceAllowanceParams, AssetType

        client = get_client()
        print("Testing connection to Polymarket CLOB...")
        print(f"Signer Address: {client.get_address()}")
        funder = os.getenv("POLYMARKET_FUNDER")
        if funder:
            print(f"Funder (proxy wallet): {funder}")

        resp = client.get_ok()
        print(f"Status OK response: {resp}")

        # py-clob-client-v2: balance lives on get_balance_allowance, not get_collateral_address
        params = BalanceAllowanceParams(asset_type=AssetType.COLLATERAL, signature_type=2)
        bal = client.get_balance_allowance(params)
        usdc = float(bal.get("balance", "0")) / 1_000_000.0
        print(f"USDC Balance: ${usdc:.2f}")

        open_orders = client.get_open_orders()
        count = len(open_orders) if isinstance(open_orders, list) else "n/a"
        print(f"Open orders: {count}")
        return True
    except Exception as e:
        print(f"Connection test failed: {e}", file=sys.stderr)
        return False

def execute_trade(slug: str, side: str, price: float, size: float):
    client = get_client()
    print(f"Fetching market details from Gamma API for slug: {slug}...")
    import requests
    url = f"https://gamma-api.polymarket.com/markets?slug={slug}"
    response = requests.get(url)
    response.raise_for_status()
    markets = response.json()
    if not markets:
        raise ValueError(f"No market found for slug {slug} on Gamma API")
    market_data = markets[0]
    
    clob_tokens = json.loads(market_data.get("clobTokenIds", "[]"))
    outcomes = json.loads(market_data.get("outcomes", "[]"))
    
    clob_token_ids = {}
    for i, token_id in enumerate(clob_tokens):
        if i < len(outcomes):
            clob_token_ids[outcomes[i].upper()] = token_id
            
    # Set default fallbacks
    if len(clob_tokens) >= 2:
        clob_token_ids["YES"] = clob_tokens[0]
        clob_token_ids["NO"] = clob_tokens[1]
        clob_token_ids["UP"] = clob_tokens[0]
        clob_token_ids["DOWN"] = clob_tokens[1]
        
    target_token_id = clob_token_ids.get(side.upper())
    if not target_token_id:
        raise ValueError(f"Could not find token ID for side {side} in outcomes {outcomes}")
        
    print(f"Targeting {side} token ID: {target_token_id}")
    # Enforce rounding and integer size for Polymarket compliance
    price = round(float(price), 2)
    size = int(size)
    
    order_args = OrderArgs(
        token_id=target_token_id,
        price=price,
        size=size,
        side="BUY"
    )
    
    resp = client.create_and_post_order(order_args)
    return resp

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Polymarket Executor")
    parser.add_argument("--test", action="store_true", help="Test connection and exit")
    parser.add_argument("--slug", type=str, help="Polymarket market slug")
    parser.add_argument("--side", type=str, choices=["YES", "NO"], help="YES or NO side")
    parser.add_argument("--price", type=float, help="Limit price")
    parser.add_argument("--size", type=float, help="Size in shares")
    
    args = parser.parse_args()
    
    if args.test:
        success = test_connection()
        sys.exit(0 if success else 1)
        
    if not (args.slug and args.side and args.price and args.size):
        parser.print_help()
        sys.exit(1)
        
    try:
        response = execute_trade(args.slug, args.side, args.price, args.size)
        print("Trade Response:")
        print(response)
    except Exception as e:
        print(f"Trade Execution Failed: {e}", file=sys.stderr)
        sys.exit(1)
