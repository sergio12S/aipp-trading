# Feature Proposal: Enhancing aipricepatterns MCP Server for Agentic Workflows & Multi-Modal Quant Trading

## Overview
The `aipricepatterns` MCP Server provides a state-of-the-art framework for pattern-similarity retrieval and out-of-sample forecast validation. During our deployment of autonomous trading loops (utilizing Google Antigravity & LLM reasoning), we identified five key architectural expansions that would establish this API as the industry standard for both autonomous AI agents and institutional quantitative desks.

---

## 1. Order Flow & Liquidity Integration (Multi-Modal Vectors)
### Problem
Matching price shapes (OHLCV) alone fails to capture the underlying cause of price movement: limit order book depth, delta absorption, and liquidity sweeps. A "Bull Flag" on thin volume behaves differently from one backed by massive passive bidding.
### Proposed Solution
Extend the HNSW index embeddings to support multi-modal features:
* **Order Book Imbalance (OBI)**: Vectorize the bid/ask depth ratios at key thresholds.
* **Cumulative Volume Delta (CVD)**: Match shapes of aggressive market buying/selling alongside price shapes.
* **API Specification Example**:
  ```json
  "embeddingMode": "pricePlusFlowV1" // Vector space combining Price Closes + CVD Cumulative Delta
  ```

---

## 2. Elastic Shape Matching via Dynamic Time Warping (DTW)
### Problem
Market structures unfold at different speeds depending on regime volatility. A "Double Bottom" reversal structure might take 20 bars in a high-volatility regime and 45 bars during low-volatility compressions. Current static length searches ($q$) miss these elastic matches.
### Proposed Solution
Integrate **Dynamic Time Warping (DTW)** distance metrics or scale-invariant sequence alignment inside the vector indexing layer. This will allow the engine to match shapes that are stretched or compressed along the time axis while preserving high similarity scores.

---

## 3. Cross-Asset Correlative Search
### Problem
Crypto assets do not trade in isolation. Altcoins are heavily dependent on BTC momentum, and crypto in general correlates with traditional equities indices (S&P500, Nasdaq, DXY).
### Proposed Solution
Support multi-dimensional vector search where the query compares shapes across multiple correlated assets simultaneously:
* **API Specification Example**:
  ```json
  {
    "symbol": "SOLUSDT",
    "correlates": [
      { "symbol": "BTCUSDT", "weight": 0.6 },
      { "symbol": "SPY", "weight": 0.4 }
    ]
  }
  ```
  This retrieves historical periods where SOL matched the target shape *specifically while* BTC and SPY matched their respective trend conditions.

---

## 4. Macro-Event Temporal Tagging
### Problem
Filtered searches currently rely on static UTC hours (`timeOfDayUTC`). However, high-impact macro news (CPI releases, FOMC meetings, NFP) occurs on specific variable dates. Finding historical analogs that occurred *strictly* during these macro distributions is currently tedious.
### Proposed Solution
Introduce a `macroEvent` catalog filter that maps timestamps to economic calendars.
* **API Specification Example**:
  ```json
  "filters": {
    "macroEvent": "CPI_RELEASE", // Filters analogs to windows ±2 hours around historical US CPI releases
    "impactLevel": "HIGH"
  }
  ```

---

## 5. Token-Efficient "Agent-Native" Output Mode
### Problem
Large JSON outputs containing full arrays of historical candle values for 50+ analogs consume significant LLM context tokens, increasing latency and API costs for autonomous agents.
### Proposed Solution
Implement a highly compressed `"embeddingMode": "agentSummary"` or `"compact": true` expansion that suppresses raw float arrays entirely and returns only pre-calculated cognitive metrics:
* **Information Coefficient (IC)** of the matches.
* **Brier Score** of the current calibration scale.
* **Z-score** of current deviation from the mean path.
* **Calibrated probability** of direction in plain markdown tables.
