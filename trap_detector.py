import os
import requests
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("TrapDetector")

class AIPPClient:
    def __init__(self, base_url="https://aipricepatterns.com/api", token=None):
        self.base_url = base_url
        self.token = token or os.getenv("AIPP_TOKEN")
        self.headers = {"Content-Type": "application/json"}
        if self.token:
            self.headers["X-Manus-Token"] = self.token

    def search_by_sketch(self, symbol: str, interval: str, query_values: list, limit: int = 10):
        url = f"{self.base_url}/v1/patterns/search-by-sketch" # Endpoint mapping to search_by_sketch
        payload = {
            "symbol": symbol,
            "interval": interval,
            "queryValues": query_values,
            "limit": limit
        }
        try:
            response = requests.post(url, json=payload, headers=self.headers)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Sketch search failed: {e}")
            return None

# Custom hand-drawn traps (normalized relative values)
TRAP_TEMPLATES = {
    "BULL_FLAG_TRAP": {
        "description": "Retail Bull Flag: Expect breakout UP. Trap strategy: SHORT the neckline breakout.",
        "values": [1.0, 1.3, 1.6, 1.8, 1.75, 1.7, 1.72, 1.65, 1.68],
        "retail_direction": "LONG",
        "counter_direction": "SHORT"
    },
    "INVERSE_HS_TRAP": {
        "description": "Retail Inverse Head & Shoulders: Expect breakout UP. Trap strategy: SHORT the neckline breakout.",
        "values": [1.0, 0.85, 0.9, 0.75, 0.7, 0.78, 0.85, 0.9, 0.82, 0.8, 0.86, 0.9, 0.95, 1.0],
        "retail_direction": "LONG",
        "counter_direction": "SHORT"
    },
    "DOUBLE_TOP_TRAP": {
        "description": "Retail Double Top: Expect breakout DOWN. Trap strategy: LONG the breakout (short squeeze).",
        "values": [1.0, 1.2, 1.1, 1.22, 1.02, 1.0],
        "retail_direction": "SHORT",
        "counter_direction": "LONG"
    }
}

class AntiRetailBot:
    def __init__(self, client: AIPPClient):
        self.client = client

    def scan_for_traps(self, symbol: str, interval: str):
        logger.info(f"Scanning {symbol} ({interval}) for retail traps...")
        
        for name, template in TRAP_TEMPLATES.items():
            logger.info(f"Evaluating template: {name} ({template['description']})")
            
            # Query AIPP sketch-search to see if current live chart resembles this template
            result = self.client.search_by_sketch(symbol, interval, template["values"], limit=10)
            if not result:
                continue
                
            # Extract matches and forecast data
            data = result.get("data", {})
            matches = data.get("matches", [])
            if not matches:
                continue
                
            # We measure average similarity of the current live chart to this template shape
            # Note: the first match represents the similarity of the current chart to the sketch
            top_match = matches[0]
            similarity = top_match.get("similarity", 0.0)
            
            logger.info(f"Current shape similarity to {name}: {similarity:.2%}")
            
            if similarity >= 0.90:
                logger.info(f"!!! MATCH DETECTED ({similarity:.2%}) for {name} !!!")
                
                # Check how historical matches resolved
                forecast = data.get("forecast", {})
                dist = forecast.get("distribution", {})
                mean_return = dist.get("mean", 0.0)
                median_return = dist.get("median", 0.0)
                
                logger.info(f"Historical Resolution stats: Mean Return = {mean_return:+.2f}% | Median = {median_return:+.2f}%")
                
                # Verify if the historical resolution favors the COUNTER direction
                # For SHORT traps, we want the historical returns to be negative (meaning price fell after breakout)
                # For LONG traps, we want historical returns to be positive
                is_trap_valid = False
                if template["counter_direction"] == "SHORT" and median_return < -1.0:
                    is_trap_valid = True
                elif template["counter_direction"] == "LONG" and median_return > 1.0:
                    is_trap_valid = True
                    
                if is_trap_valid:
                    logger.info(f"✅ TRAP VERIFIED. Generating counter-trade signal!")
                    print(f"\n=========================================")
                    print(f"🚨 SIGNAL DETECTED: COUNTER-TRADE {template['counter_direction']} on {symbol}")
                    print(f"Reason: Retail shape '{name}' matched with {similarity:.1%} similarity.")
                    print(f"Historical Trap Resolution: {template['counter_direction']} yields median {abs(median_return):.2f}% profit.")
                    print(f"=========================================\n")
                else:
                    logger.info("Trap setup detected, but historical returns did not meet safety threshold.")
            else:
                logger.info(f"No match for {name} (similarity below threshold).")

if __name__ == "__main__":
    client = AIPPClient()
    bot = AntiRetailBot(client)
    # bot.scan_for_traps("BTCUSDT", "15m")
