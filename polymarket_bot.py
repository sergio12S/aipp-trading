import os
import time
import json
import logging
import requests

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("PolymarketBot")

class AIPPPolymarketClient:
    def __init__(self, base_url="https://aipricepatterns.com/api", token=None):
        self.base_url = base_url
        self.token = token or os.getenv("AIPP_TOKEN")
        self.headers = {"Content-Type": "application/json"}
        if self.token:
            self.headers["X-Manus-Token"] = self.token

    def get_live_decision(self):
        # Maps to get_live_polymarket_trade_decision
        url = f"{self.base_url}/v1/polymarket/live-trade-decision"
        try:
            response = requests.post(url, json={}, headers=self.headers, timeout=20)
            if response.status_code == 404:
                # Try fallback endpoint
                url_fallback = f"{self.base_url}/v1/polymarket/live-decision"
                response = requests.post(url_fallback, json={}, headers=self.headers, timeout=20)
            
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Failed to fetch Polymarket live decision: {e}")
            return None

class PolymarketPaperBot:
    def __init__(self, client: AIPPPolymarketClient, trades_file="active_paper_trades.json", ledger_file="paper_trading_ledger.json"):
        self.client = client
        self.trades_file = trades_file
        self.ledger_file = ledger_file
        self.active_trades = self.load_json(self.trades_file, [])
        self.ledger = self.load_json(self.ledger_file, {"total_trades": 0, "wins": 0, "losses": 0, "net_pnl_usd": 0.0, "history": []})

    def load_json(self, path, default):
        if os.path.exists(path):
            try:
                with open(path, "r") as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"Error loading {path}: {e}")
        return default

    def save_json(self, path, data):
        try:
            with open(path, "w") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.error(f"Error saving {path}: {e}")

    def record_trade(self, decision_card):
        market = decision_card.get("market", {})
        decision = decision_card.get("decision", {})
        action = decision.get("action")
        
        if action not in ["BUY_YES", "BUY_NO"]:
            logger.info("Decision is SKIP. No paper trade recorded.")
            return

        side = decision.get("side")
        market_id = market.get("marketId")
        slug = market.get("slug")
        
        # Check if we already have an active trade in this market
        if any(t["market_id"] == market_id for t in self.active_trades):
            logger.info(f"Already holding a paper position in market {slug}.")
            return

        # Calculate entry price based on bid/ask
        contract_info = market.get(side.lower(), {})
        ask_price = contract_info.get("ask", 0.5)
        
        # Simulated allocation
        size_fraction = decision.get("sizeFraction", 0.05)
        simulated_balance = 1000.0  # $1,000 paper account
        capital_allocated = simulated_balance * size_fraction
        shares_bought = capital_allocated / ask_price

        trade_record = {
            "market_id": market_id,
            "slug": slug,
            "title": market.get("title"),
            "side": side,
            "strike_price": market.get("strikePrice"),
            "entry_price": ask_price,
            "shares": shares_bought,
            "cost_usd": capital_allocated,
            "end_date": market.get("endDate"),
            "entry_time": time.time(),
            "p_yes": decision_card.get("combined", {}).get("pYes", 0.5)
        }

        self.active_trades.append(trade_record)
        self.save_json(self.trades_file, self.active_trades)
        
        logger.info(f"📝 PAPER TRADE ENTERED: Bought {shares_bought:.2f} shares of {side} in {slug} at ${ask_price:.2f} (Cost: ${capital_allocated:.2f})")

    def check_resolutions(self):
        if not self.active_trades:
            return

        logger.info("Checking resolutions for active paper trades...")
        # To check resolutions, we query a fresh decision card to get the current price of BTC
        decision_card = self.client.get_live_decision()
        if not decision_card:
            return

        current_btc_price = decision_card.get("pattern", {}).get("currentPrice")
        if not current_btc_price:
            return

        remaining_trades = []
        for trade in self.active_trades:
            # We check if the contract has expired (we can use time, but here we can check the new market's title or timestamp)
            # The AIPP endDate is ISO string, e.g. "2026-07-18T20:15:00Z"
            # Let's convert current epoch time to UTC and check if it is past end_date
            import datetime
            try:
                end_dt = datetime.datetime.strptime(trade["end_date"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=datetime.timezone.utc)
                now_dt = datetime.datetime.now(datetime.timezone.utc)
            except Exception as e:
                logger.error(f"Error parsing date {trade['end_date']}: {e}")
                remaining_trades.append(trade)
                continue

            if now_dt > end_dt:
                # Contract resolved!
                strike = trade["strike_price"]
                side = trade["side"]
                
                # Check if YES won or NO won
                # YES wins if expiry BTC price > strike price
                yes_won = current_btc_price > strike
                win = (side == "YES" and yes_won) or (side == "NO" and not yes_won)
                
                payout = 1.0 if win else 0.0
                revenue = trade["shares"] * payout
                pnl = revenue - trade["cost_usd"]
                
                # Update ledger
                self.ledger["total_trades"] += 1
                if win:
                    self.ledger["wins"] += 1
                else:
                    self.ledger["losses"] += 1
                self.ledger["net_pnl_usd"] += pnl
                
                trade["exit_price"] = payout
                trade["pnl_usd"] = pnl
                trade["resolved_btc_price"] = current_btc_price
                trade["win"] = win
                
                self.ledger["history"].append(trade)
                
                logger.info(f"🏆 PAPER TRADE RESOLVED: {trade['slug']} ({side}) | Final Price: {current_btc_price} vs Strike: {strike} | Result: {'WIN' if win else 'LOSS'} (PnL: ${pnl:+.2f})")
            else:
                remaining_trades.append(trade)

        self.active_trades = remaining_trades
        self.save_json(self.trades_file, self.active_trades)
        self.save_json(self.ledger_file, self.ledger)

    # =========================================================================
    # PLACEHOLDERS FOR REAL BLOCKCHAIN EXECUTION (FOR FUTURE USE)
    # =========================================================================
    def execute_blockchain_trade(self, side: str, market_id: str, ask_price: float, size_usd: float):
        """
        Placeholder for real executions on Polygon.
        Requires py-polymarket-clob SDK and private key setup.
        
        Example setup:
        from py_polymarket_clob_client.client import ClobClient
        client = ClobClient(
            host="https://clob.polymarket.com",
            key=os.getenv("POLYGON_PRIVATE_KEY"),
            chain_id=137
        )
        # 1. Approve USDC spending for Polymarket CTF contract
        # 2. Place limit order:
        # client.create_order(market_id, side="BUY", price=ask_price, size=shares)
        """
        logger.warning("REAL BLOCKCHAIN TRADE CALLED: Blockchain execution is currently disabled. Running in Paper Mode.")
        pass

if __name__ == "__main__":
    client = AIPPPolymarketClient()
    bot = PolymarketPaperBot(client)
    
    # Run once
    decision = client.get_live_decision()
    if decision:
        bot.check_resolutions()
        bot.record_trade(decision)
