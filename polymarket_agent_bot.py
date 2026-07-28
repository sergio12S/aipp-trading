import os
import sys
import argparse
import requests
import json
import logging
from polymarket_executor import get_client, execute_trade
from py_clob_client_v2.clob_types import BalanceAllowanceParams, AssetType

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("PolymarketAgentBot")

class PolymarketAgentBot:
    def __init__(self, aipp_base_url="https://aipricepatterns.com/api", aipp_token=None):
        self.aipp_base_url = aipp_base_url
        self.aipp_token = aipp_token or os.getenv("AIPP_TOKEN")
        self.headers = {"Content-Type": "application/json"}
        if self.aipp_token:
            self.headers["X-Manus-Token"] = self.aipp_token

    def get_live_decision(self):
        url = f"{self.aipp_base_url}/v1/polymarket/live-trade-decision"
        payload = {
            "symbol": "BTCUSDT",
            "interval": "15m",
            "minEdge": 0.03,
            "minCombinedConfidence": 0.12
        }
        try:
            response = requests.post(url, json=payload, headers=self.headers, timeout=20)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Failed to fetch live decision from AIPP: {e}")
            return None

    def get_usdc_balance(self, client):
        try:
            params = BalanceAllowanceParams(asset_type=AssetType.COLLATERAL, signature_type=2)
            res = client.get_balance_allowance(params)
            raw_balance = float(res.get("balance", "0"))
            return raw_balance / 1_000_000.0
        except Exception as e:
            logger.error(f"Failed to get USDC balance from Polymarket: {e}")
            return 0.0

    def update_history_and_get_trend(self, new_strike, prev_close):
        history_file = os.path.join(os.path.dirname(__file__), "strike_history.json")
        history = []
        if os.path.exists(history_file):
            try:
                with open(history_file, "r") as f:
                    history = json.load(f)
            except Exception:
                pass
                
        # 1. Update the close price and result for the previous contract (last item in history)
        if history:
            last_item = history[-1]
            if last_item.get("close") is None or last_item.get("close") == 0:
                last_item["close"] = float(prev_close)
                last_item["result"] = "YES" if float(prev_close) >= float(last_item["strike"]) else "NO"
                
        # 2. Calculate short term trend based on the last 3 resolved strikes
        trend = "NEUTRAL"
        if len(history) >= 3:
            s1 = float(history[-3]["strike"])
            s2 = float(history[-2]["strike"])
            s3 = float(history[-1]["strike"])
            if s3 > s2 > s1:
                trend = "UP"
            elif s3 < s2 < s1:
                trend = "DOWN"
                
        # 3. Append the new contract's strike price (close will be filled in the next iteration)
        history.append({
            "time": "now",
            "strike": float(new_strike),
            "close": None,
            "result": None
        })
        
        # Keep history file bounded to last 50 entries
        if len(history) > 50:
            history = history[-50:]
            
        # Save back to file
        try:
            with open(history_file, "w") as f:
                json.dump(history, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save strike history: {e}")
            
        return trend

    def run_cycle(self, dry_run=False):
        logger.info("Starting trading cycle...")
        
        # 1. Initialize Polymarket client to verify credentials and check balance
        try:
            client = get_client()
        except Exception as e:
            logger.error(f"Failed to initialize Polymarket client: {e}")
            return
            
        usdc_balance = self.get_usdc_balance(client)
        logger.info(f"Polymarket USDC Balance: ${usdc_balance:.2f}")
        
        if usdc_balance < 2.0:
            logger.warning("USDC balance is too low to place trades (minimum effective size is ~$2.00-$2.50).")
            if not dry_run:
                logger.warning("Running in DRY RUN mode because of low balance.")
                dry_run = True

        # 2. Get live decision card
        decision_card = self.get_live_decision()
        if not decision_card:
            logger.error("Could not fetch trade decision card.")
            return

        # Unpack the 'data' key if present
        card_data = decision_card.get("data", decision_card) if isinstance(decision_card, dict) else {}
        market = card_data.get("market", {})
        decision = card_data.get("decision", {})
        
        market_id = market.get("marketId")
        slug = market.get("slug")
        title = market.get("title")
        strike = market.get("strikePrice")
        current_btc = market.get("currentPrice")
        action = decision.get("action")  # BUY_YES, BUY_NO, SKIP
        side = decision.get("side")      # YES, NO
        
        # Update history and calculate trend
        if strike and current_btc:
            trend = self.update_history_and_get_trend(strike, current_btc)
            logger.info(f"Market short-term trend: {trend}")
        else:
            trend = "NEUTRAL"
            
        print("\n" + "="*60)
        print(f"📊 MARKET: {title}")
        print(f"Strike Price: {strike} | Current BTC: {current_btc} | Trend: {trend}")
        print(f"Live Price YES: {market.get('yes', {}).get('ask')} | NO: {market.get('no', {}).get('ask')}")
        print(f"Decision Action: {action} (Max Entry: {decision.get('entryPriceMax')})")
        print("="*60 + "\n")

        if action == "SKIP" or not side:
            logger.info(f"SKIP signal or missing side. Reasons: {decision.get('skipReasons') or 'No Edge'}")
            return

        # Hard G5 Trend Filter: BUY_YES allowed only in UP trend; BUY_NO allowed only in DOWN trend
        if (side.upper() == "YES" and trend != "UP") or (side.upper() == "NO" and trend != "DOWN"):
            logger.warning(f"G5 Trend filter block: signal is BUY_{side} but market trend is '{trend}'. Skipping trade.")
            return

        # 3. Sizing & pricing
        max_entry = decision.get("entryPriceMax", 1.0)
        size_fraction = decision.get("sizeFraction", 0.05)
        
        # Get actual ask price from market details
        ask_price = market.get(side.lower(), {}).get("ask", max_entry)
        
        if ask_price > max_entry:
            logger.warning(f"Market price ({ask_price}) is higher than max entry limit ({max_entry}). Skipping trade.")
            return

        # Allocate capital ($2.0 USDC for minimal safe bets)
        allocated_usd = 2.0

        if allocated_usd > usdc_balance:
            logger.warning(f"Not enough USDC balance (${usdc_balance:.2f}) to place the $2.00 order.")
            return

        # Round ask price to 2 decimals (tick size $0.01)
        ask_price = round(ask_price, 2)

        # Calculate shares (must be integer number of contracts)
        shares = int(allocated_usd / ask_price)
        if shares < 5:
            shares = 5  # minimum 5 tokens/shares

        logger.info(f"Signal: BUY_{side} | Shares: {shares} | Target Price: ${ask_price:.2f} (Total: ${shares * ask_price:.2f} USDC)")

        if dry_run:
            logger.info(f"🛑 [DRY RUN] Would place order: BUY {shares} shares of {side} on market {slug} at max price {ask_price}")
            return

        # 4. Execute Trade
        try:
            logger.info(f"🚀 Executing REAL trade on Polymarket...")
            resp = execute_trade(slug, side, ask_price, shares)
            print("\n✅ ORDER PLACED SUCCESSFULLY!")
            print(json.dumps(resp, indent=2))
        except Exception as e:
            logger.error(f"❌ Execution failed: {e}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Polymarket LLM-Agent Bot")
    parser.add_argument("--dry-run", action="store_true", help="Run without placing real trades")
    args = parser.parse_args()

    bot = PolymarketAgentBot()
    bot.run_cycle(dry_run=args.dry_run)
