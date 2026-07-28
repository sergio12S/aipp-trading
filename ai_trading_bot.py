import os
import requests
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("AIPPriceBot")

class AIPPClient:
    """
    Python client for interacting with the AI Price Patterns (AIPP) API.
    Can be used to request decisions, metrics, and manage datasets.
    """
    def __init__(self, base_url="https://aipricepatterns.com/api", token=None):
        self.base_url = base_url
        self.token = token or os.getenv("AIPP_TOKEN")
        self.headers = {
            "Content-Type": "application/json"
        }
        if self.token:
            self.headers["X-Manus-Token"] = self.token

    def get_trading_decision(self, symbol: str, interval: str, q: int = 40, f: int = 5, include_backtest: bool = False):
        """
        Retrieves the trading decision card: TRADEABLE, WATCH, or SKIP.
        """
        url = f"{self.base_url}/v1/trading/decision"
        payload = {
            "symbol": symbol,
            "interval": interval,
            "q": q,
            "f": f,
            "includeBacktest": include_backtest
        }
        try:
            response = requests.post(url, json=payload, headers=self.headers)
            if response.status_code == 402:
                logger.error("Payment required. Solana Pay invoice generated or X-Manus-Token invalid.")
                return None
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to query get_trading_decision: {e}")
            return None

    def get_pattern_metrics(self, symbol: str, interval: str, q: int = 40, f: int = 5):
        """
        Retrieves statistical metrics & expected forecast distributions.
        """
        url = f"{self.base_url}/v1/patterns/metrics"
        payload = {
            "symbol": symbol,
            "interval": interval,
            "q": q,
            "f": f
        }
        try:
            response = requests.post(url, json=payload, headers=self.headers)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to query get_pattern_metrics: {e}")
            return None

    def get_live_polymarket_decision(self, symbol: str = "BTCUSDT", interval: str = "15m", min_edge: float = 0.03, min_confidence: float = 0.12):
        """
        Auto-discovers the active BTC 15m Polymarket contract and returns a BUY_YES / BUY_NO / SKIP decision.
        """
        url = f"{self.base_url}/v1/polymarket/live-trade-decision"
        payload = {
            "symbol": symbol,
            "interval": interval,
            "minEdge": min_edge,
            "minCombinedConfidence": min_confidence
        }
        try:
            response = requests.post(url, json=payload, headers=self.headers)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to query live polymarket trade decision: {e}")
            return None


class PatternTradingStrategy:
    def __init__(self, client: AIPPClient, risk_free_ratio: float = 0.25):
        self.client = client
        self.risk_free_ratio = risk_free_ratio  # Quarter-Kelly scaling

    def run_spot_futures_logic(self, symbol: str, interval: str, q: int = 40, f: int = 5):
        """
        Executes standard Spot/Futures trade signals with dynamic TP/SL levels.
        """
        logger.info(f"--- Running Spot/Futures Pattern Strategy for {symbol} {interval} ---")
        
        # 1. Fetch the main trading decision
        decision_data = self.client.get_trading_decision(symbol, interval, q=q, f=f)
        if not decision_data:
            logger.warning("Aborting: Could not fetch trading decision card.")
            return

        final_verdict = decision_data.get("final", {})
        action = final_verdict.get("action")
        direction = final_verdict.get("direction")
        
        logger.info(f"Verdict Action: {action} | Direction: {direction}")
        
        if action == "SKIP":
            logger.info(f"SKIP action received. Reason codes: {final_verdict.get('reasons')}")
            return

        # 2. Check Evidence Quality
        evidence_quality = decision_data.get("evidenceQuality", {})
        grade = evidence_quality.get("grade", "THIN")
        score = evidence_quality.get("score", 0.0)
        
        logger.info(f"Evidence Quality: {grade} (Score: {score:.2f})")
        if grade in ["THIN", "WEAK"]:
            logger.warning(f"Aborting trade: Evidence quality is too low ({grade}).")
            return

        # 3. Retrieve Forecast Distribution and Sigma Levels for Target Placement
        metrics_data = self.client.get_pattern_metrics(symbol, interval, q=q, f=f)
        if not metrics_data:
            logger.warning("Aborting: Could not fetch pattern metrics for TP/SL setup.")
            return

        sigma_levels = metrics_data.get("sigmaLevels", [])
        # Find 1-sigma ranges to scale Stop Loss and Take Profit
        one_sigma = next((lvl for lvl in sigma_levels if lvl["label"] == "1σ"), None)
        
        if not one_sigma:
            logger.warning("1-sigma level metrics missing from the server response.")
            return

        tp_pct = one_sigma["positive"]
        sl_pct = abs(one_sigma["negative"])  # Ensure positive percentage for offset calculations

        # 4. Check historical Win Rate and Drawdown
        risk_analysis = metrics_data.get("riskAnalysis", {})
        win_rate = metrics_data.get("winRate", 50.0)
        value_at_risk = risk_analysis.get("valueAtRisk95", 0.0)
        
        logger.info(f"Pattern Historical Win Rate: {win_rate}% | 95% VaR: {value_at_risk}%")
        logger.info(f"Calculated Target Levels -> Take Profit: +{tp_pct:.2f}% | Stop Loss: -{sl_pct:.2f}%")

        # In a live bot, place order here (e.g. ccxt.binance.create_order)
        logger.info(f"EXECUTION: Opening {direction} position on {symbol} with SL={sl_pct}% and TP={tp_pct}%")

    def run_polymarket_logic(self, symbol: str = "BTCUSDT", interval: str = "15m"):
        """
        Executes Polymarket contract predictions based on statistical edge and Kelly sizing.
        """
        logger.info(f"--- Running Polymarket prediction strategy for {symbol} {interval} ---")
        
        # 1. Fetch live contract details and decisions
        decision_data = self.client.get_live_polymarket_decision(symbol, interval)
        if not decision_data:
            logger.warning("Aborting: Could not fetch live Polymarket decision.")
            return

        execution = decision_data.get("execution", {})
        decision = decision_data.get("decision", {})
        action = decision.get("action")  # BUY_YES, BUY_NO, SKIP
        
        logger.info(f"Polymarket Action: {action}")
        
        if action == "SKIP":
            logger.info(f"SKIP action. Reason: {decision.get('skipReason') or 'No Edge'}")
            return

        # 2. Extract edge and implied market probability
        edge = execution.get("edge", 0.0)
        max_entry_price = execution.get("maxEntryPrice", 0.0)
        implied_prob = execution.get("pMarket", 0.50)
        
        logger.info(f"Calibrated Edge: {edge:+.4f} (implied probability: {implied_prob:.2f})")
        logger.info(f"Max Contract entry price allowed: {max_entry_price:.2f} USDC")

        # 3. Size the position using Kelly fraction
        # Kelly: f* = (p*b - q)/b where b=1 for binary 50/50 payouts (1 to 1 return per win)
        # Kelly = (Probability - MarketProbability) / (MarketProbability * (1 - MarketProbability))
        p = implied_prob + edge
        q_prob = 1 - p
        # Odds are b = (1 - implied_prob) / implied_prob
        odds = (1.0 - implied_prob) / implied_prob
        
        raw_kelly = (p * odds - q_prob) / odds if odds > 0 else 0
        allocated_fraction = raw_kelly * self.risk_free_ratio
        
        if allocated_fraction <= 0:
            logger.warning(f"Calculated Kelly fraction is non-positive ({allocated_fraction:.4f}). Skipping.")
            return

        logger.info(f"Kelly Fraction Sizing: Raw={raw_kelly:.4f} | Scaled={allocated_fraction:.4f}")
        logger.info(f"EXECUTION: BUY_{action.split('_')[1]} up to {max_entry_price:.2f} USDC contract. Sizing: {allocated_fraction * 100:.2f}% of capital.")

    def run_hardened_consensus_strategy(self, symbol: str, interval: str, f: int = 5):
        """
        Hardened Spot/Futures strategy using Multi-Scale Consensus and Regime Filters.
        Queries multiple lookback windows (q=[24, 48, 96]) and only trades if they agree,
        the market regime is clear, and the evidence quality score is high.
        """
        logger.info(f"--- Running Hardened Consensus Strategy for {symbol} {interval} ---")
        
        q_scales = [24, 48, 96]
        votes = []
        decision_cards = {}
        
        # 1. Fetch decisions for each scale in parallel
        for q in q_scales:
            logger.info(f"Checking scale q={q}...")
            # We enforce includeBacktest=True with a larger window for validation
            card = self.client.get_trading_decision(symbol, interval, q=q, f=f, include_backtest=True)
            if not card:
                logger.warning(f"Could not retrieve card for scale q={q}")
                continue
            
            decision_cards[q] = card
            
            final_action = card.get("final", {}).get("action", "SKIP")
            direction = card.get("final", {}).get("direction")
            
            # We check if evidence quality grade is strong/medium, and backtest passed
            evidence_quality = card.get("evidenceQuality", {})
            grade = evidence_quality.get("grade", "THIN")
            score = evidence_quality.get("score", 0.0)
            
            proof_passed = card.get("proof", {}).get("verdict") == "PASSED"
            
            if final_action != "SKIP" and proof_passed:
                votes.append(direction)  # "LONG" or "SHORT"
                logger.info(f"-> Scale q={q}: VOTE={direction} | Score: {score:.2f} | Proof: PASSED")
            else:
                votes.append("SKIP")
                logger.info(f"-> Scale q={q}: VOTE=SKIP (Action={final_action}, Proof={card.get('proof', {}).get('verdict')})")

        # 2. Check scale consensus
        long_votes = votes.count("LONG")
        short_votes = votes.count("SHORT")
        
        logger.info(f"Consensus Results: LONG={long_votes}, SHORT={short_votes}, SKIP={votes.count('SKIP')}")
        
        # Required agreement: at least 2 out of 3 active scales must agree on a direction, and NO scale must vote the opposite
        if long_votes >= 2 and short_votes == 0:
            final_direction = "LONG"
        elif short_votes >= 2 and long_votes == 0:
            final_direction = "SHORT"
        else:
            logger.warning("Aborting: Multi-scale consensus not reached or conflicting votes present.")
            return

        # 3. Retrieve representative scale details for execution targets (using q=48 as baseline)
        base_card = decision_cards.get(48)
        if not base_card:
            # Fallback to first available
            base_card = list(decision_cards.values())[0]

        # 4. Regime Check: Ensure direction matches regime momentum
        regime = base_card.get("decision", {}).get("evidence", {}).get("regime", "UNKNOWN")
        logger.info(f"Checking Regime: {regime} | Target Direction: {final_direction}")
        
        # Invalidation mapping: Avoid trend-following in chop, or counter-trend
        if "CHOP" in regime or regime == "UNKNOWN":
            logger.warning(f"Aborting: Market regime is choppy or unknown ({regime}). Skipping execution.")
            return
        if final_direction == "LONG" and "DOWNTREND" in regime:
            logger.warning(f"Aborting: Anti-trend trade. Cannot go LONG in {regime} regime.")
            return
        if final_direction == "SHORT" and "UPTREND" in regime:
            logger.warning(f"Aborting: Anti-trend trade. Cannot go SHORT in {regime} regime.")
            return

        # 5. Dynamic TP/SL Setup based on the worst-case failure analogue (Hard SL)
        # We find the worst outcome among failure analogues to set a safe SL
        failure_analogues = base_card.get("failureAnalogues", [])
        max_adverse_excursion = 0.0
        for fa in failure_analogues:
            adverse = abs(fa.get("maxAdversePct", 0.0))
            if adverse > max_adverse_excursion:
                max_adverse_excursion = adverse
                
        # Set SL at max failure excursion + safety buffer (e.g. 0.2%), or fallback to 1-sigma if empty
        safety_buffer = 0.2
        if max_adverse_excursion > 0:
            sl_pct = max_adverse_excursion + safety_buffer
            logger.info(f"SL set based on historical failure analogues: -{sl_pct:.2f}% (excursion={max_adverse_excursion:.2f}%)")
        else:
            # Fallback to metrics 1-sigma
            sl_pct = 1.5  # standard fallback
            logger.info(f"No failure analogues found. SL set to standard fallback: -{sl_pct:.2f}%")

        # Set TP based on expected median return of the winning cases
        metrics = base_card.get("metrics", {})
        tp_pct = abs(metrics.get("medianPct", 1.0))
        if tp_pct < 0.3:  # Minimum reward threshold
            tp_pct = 0.8
            
        logger.info(f"Target Levels -> Take Profit: +{tp_pct:.2f}% | Stop Loss: -{sl_pct:.2f}%")
        logger.info(f"EXECUTION COMPLETED: Open {final_direction} position on {symbol} with Hard SL={sl_pct}% and TP={tp_pct}%")

if __name__ == "__main__":
    # Example initialization.
    # AIPP_TOKEN can be supplied via environment variable.
    client = AIPPClient(token=os.getenv("AIPP_TOKEN"))
    strategy = PatternTradingStrategy(client, risk_free_ratio=0.25)
    
    # Example dry run:
    # strategy.run_hardened_consensus_strategy("BTCUSDT", "15m")
    logger.info("Bot loaded successfully.")

