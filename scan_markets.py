import os
import requests
import logging
import time

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("MarketScanner")

class AIPPClient:
    def __init__(self, base_url="https://aipricepatterns.com/api", token=None):
        self.base_url = base_url
        self.token = token or os.getenv("AIPP_TOKEN")
        self.headers = {"Content-Type": "application/json"}
        if self.token:
            self.headers["X-Manus-Token"] = self.token

    def get_trading_decision(self, symbol: str, interval: str, q: int = 40, f: int = 5, include_backtest: bool = True):
        # We target the endpoint that maps to the MCP tool get_trading_decision
        # Since this script runs locally, we can make it call the REST endpoint of the platform
        url = f"{self.base_url}/v1/trading/decision"
        payload = {
            "symbol": symbol,
            "interval": interval,
            "q": q,
            "f": f,
            "includeBacktest": include_backtest,
            "backtestMaxBars": 1500  # Reasonable history size for quick proofing
        }
        try:
            response = requests.post(url, json=payload, headers=self.headers, timeout=15)
            if response.status_code == 402:
                logger.error(f"Payment required for {symbol} {interval}.")
                return None
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to query {symbol} {interval}: {e}")
            return None

def main():
    # In a local execution, we would call the actual AIPP API.
    # For this exercise, let's create a script that can scan Binance symbols.
    client = AIPPClient()
    symbols = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT"]
    intervals = ["15m", "1h", "4h"]
    
    logger.info("Starting market scan across AIPP symbols...")
    
    active_setups = []
    
    for symbol in symbols:
        for interval in intervals:
            logger.info(f"Scanning {symbol} on {interval} timeframe...")
            decision = client.get_trading_decision(symbol, interval, q=40, f=5, include_backtest=True)
            
            if not decision:
                continue
                
            final = decision.get("final", {})
            action = final.get("action")
            direction = final.get("direction")
            confidence = final.get("confidence", 0.0)
            
            # Print basic log for each
            logger.info(f"-> Result: {action} ({direction}) | Confidence: {confidence:.2%}")
            
            if action != "SKIP":
                logger.info(f"*** FOUND TRADEABLE SETUP: {symbol} {interval} {direction} (Confidence: {confidence:.2%}) ***")
                proof = decision.get("proof", {})
                if proof:
                    logger.info(f"Proof Stats: WinRate={proof.get('stats', {}).get('winRate')}% | Sharpe={proof.get('stats', {}).get('sharpeRatio')}")
                active_setups.append({
                    "symbol": symbol,
                    "interval": interval,
                    "action": action,
                    "direction": direction,
                    "confidence": confidence,
                    "decision": decision
                })
            
            # Small sleep to respect rate limits
            time.sleep(1.0)
            
    logger.info("--- Scan Completed ---")
    if not active_setups:
        logger.info("No active tradeable setups found (all returned SKIP or WATCH). This is expected during low-confidence market regimes.")
    else:
        logger.info(f"Found {len(active_setups)} active setup(s):")
        for setup in active_setups:
            print(f"- {setup['symbol']} {setup['interval']}: {setup['action']} {setup['direction']} (Confidence: {setup['confidence']:.1%})")

if __name__ == "__main__":
    main()
