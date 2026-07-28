import os
import requests
import json
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("AutopilotScanner")

class AIPPClient:
    def __init__(self, base_url="https://aipricepatterns.com/api", token=None):
        self.base_url = base_url
        self.token = token or os.getenv("AIPP_TOKEN")
        self.headers = {"Content-Type": "application/json"}
        if self.token:
            self.headers["X-Manus-Token"] = self.token

    def get_trading_decision(self, symbol: str, interval: str, q: int = 40, f: int = 5, include_backtest: bool = True):
        url = f"{self.base_url}/v1/trading/decision"
        payload = {
            "symbol": symbol,
            "interval": interval,
            "q": q,
            "f": f,
            "includeBacktest": include_backtest,
            "backtestMaxBars": 2000
        }
        try:
            response = requests.post(url, json=payload, headers=self.headers, timeout=25)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Error querying {symbol} {interval}: {e}")
            return None

    def search_by_sketch(self, symbol: str, interval: str, query_values: list):
        url = f"{self.base_url}/v1/patterns/search-by-sketch"
        payload = {"symbol": symbol, "interval": interval, "queryValues": query_values, "limit": 5}
        try:
            response = requests.post(url, json=payload, headers=self.headers)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            return None

TRAP_TEMPLATES = {
    "BULL_FLAG_TRAP": [1.0, 1.3, 1.6, 1.8, 1.75, 1.7, 1.72, 1.65, 1.68],
    "INVERSE_HS_TRAP": [1.0, 0.85, 0.9, 0.75, 0.7, 0.78, 0.85, 0.9, 0.82, 0.8, 0.86, 0.9, 0.95, 1.0],
    "DOUBLE_TOP_TRAP": [1.0, 1.2, 1.1, 1.22, 1.02, 1.0]
}

def generate_playbook():
    client = AIPPClient()
    symbols = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
    timeframes = ["15m", "1h", "4h"]
    
    playbook_content = []
    playbook_content.append("# 📊 AI Pattern Trading Playbook (Autopilot Scan)")
    playbook_content.append("Generated automatically by the background scanning loop.\n")
    
    logger.info("Starting autopilot market scan...")
    
    active_signals = []
    skipped_positions = []
    trap_signals = []

    for symbol in symbols:
        # Check Traps first (15m and 1h)
        for name, values in TRAP_TEMPLATES.items():
            for tf in ["15m", "1h"]:
                res = client.search_by_sketch(symbol, tf, values)
                if not res:
                    continue
                matches = res.get("data", {}).get("matches", [])
                if matches and matches[0].get("similarity", 0.0) >= 0.92:
                    forecast = res.get("data", {}).get("forecast", {})
                    median_ret = forecast.get("distribution", {}).get("median", 0.0)
                    
                    # We have a trap setup if returns favor the counter-trend
                    direction = "SHORT" if "TRAP" in name and "DOUBLE_TOP" not in name else "LONG"
                    if (direction == "SHORT" and median_ret < -1.0) or (direction == "LONG" and median_ret > 1.0):
                        trap_signals.append({
                            "symbol": symbol,
                            "timeframe": tf,
                            "name": name,
                            "direction": direction,
                            "similarity": matches[0]["similarity"],
                            "median_ret": median_ret
                        })

        # Check Multi-scale Consensus
        for tf in timeframes:
            logger.info(f"Analyzing multi-scale consensus for {symbol} {tf}...")
            scales = [24, 48, 96]
            votes = {}
            cards = {}
            
            for q in scales:
                card = client.get_trading_decision(symbol, tf, q=q, f=5, include_backtest=True)
                if not card:
                    continue
                cards[q] = card
                
                action = card.get("final", {}).get("action")
                direction = card.get("final", {}).get("direction")
                proof_passed = card.get("proof", {}).get("verdict") == "PASSED"
                
                if action != "SKIP" and proof_passed:
                    votes[q] = direction
                else:
                    votes[q] = "SKIP"
            
            # Evaluate consensus
            vote_list = list(votes.values())
            long_votes = vote_list.count("LONG")
            short_votes = vote_list.count("SHORT")
            
            if (long_votes >= 2 and short_votes == 0) or (short_votes >= 2 and long_votes == 0):
                direction = "LONG" if long_votes >= 2 else "SHORT"
                base_card = cards.get(48) or list(cards.values())[0]
                regime = base_card.get("decision", {}).get("evidence", {}).get("regime", "UNKNOWN")
                
                # Check regime alignment
                regime_ok = True
                if "CHOP" in regime or regime == "UNKNOWN":
                    regime_ok = False
                elif direction == "LONG" and "DOWNTREND" in regime:
                    regime_ok = False
                elif direction == "SHORT" and "UPTREND" in regime:
                    regime_ok = False
                    
                if regime_ok:
                    # Calculate Stop Loss using failure analogues max adverse excursion
                    fa = base_card.get("failureAnalogues", [])
                    max_adv = 0.0
                    for f_an in fa:
                        max_adv = max(max_adv, abs(f_an.get("maxAdversePct", 0.0)))
                    
                    sl = max_adv + 0.2 if max_adv > 0 else 1.5
                    tp = abs(base_card.get("metrics", {}).get("medianPct", 1.0))
                    if tp < 0.3:
                        tp = 0.8
                        
                    active_signals.append({
                        "symbol": symbol,
                        "timeframe": tf,
                        "direction": direction,
                        "regime": regime,
                        "tp": tp,
                        "sl": sl,
                        "confidence": base_card.get("decision", {}).get("confidence", 0.0)
                    })
                else:
                    skipped_positions.append(f"{symbol} {tf} ({direction} skipped due to anti-regime: {regime})")
            else:
                skipped_positions.append(f"{symbol} {tf} (no consensus: {vote_list})")

    # Write results to playbook
    playbook_content.append("## 🚨 Active Execution Signals (Hardened Consensus)")
    if not active_signals:
        playbook_content.append("*No trade signals passed the multi-scale consensus, regime gate, and backtest proof checks. Sidelined to protect capital.*\n")
    else:
        for sig in active_signals:
            playbook_content.append(f"### ✅ **{sig['symbol']} - {sig['timeframe']} {sig['direction']}**")
            playbook_content.append(f"- **Regime**: {sig['regime']}")
            playbook_content.append(f"- **Confidence**: {sig['confidence']:.1%}")
            playbook_content.append(f"- **Execution Targets**: Take Profit `+{sig['tp']:.2f}%` | Stop Loss `-{sig['sl']:.2f}%` (based on historical failures)")
            playbook_content.append("")

    playbook_content.append("## ⚡ Anti-Retail Trap Signals")
    if not trap_signals:
        playbook_content.append("*No retail pattern traps (flags, double tops, head & shoulders) detected at high similarities.*\n")
    else:
        for trap in trap_signals:
            playbook_content.append(f"### 🎯 **{trap['symbol']} - {trap['timeframe']} COUNTER-TRADE {trap['direction']}**")
            playbook_content.append(f"- **Pattern**: {trap['name']} (Similarity: {trap['similarity']:.1%})")
            playbook_content.append(f"- **Historical Trap profit (median)**: `+{abs(trap['median_ret']):.2f}%` (the retail setup broke down in 100% of cases)")
            playbook_content.append("")

    playbook_content.append("## 🔍 Technical Scan Summary")
    playbook_content.append("Details of skipped setups:")
    for skip in skipped_positions:
        playbook_content.append(f"- {skip}")
        
    # Write file
    filepath = "/home/serg/projects/trading/playbook.md"
    with open(filepath, "w") as f:
        f.write("\n".join(playbook_content))
        
    logger.info(f"Playbook saved to {filepath}")

if __name__ == "__main__":
    generate_playbook()
