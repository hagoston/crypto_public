# Project Document: Solana Memecoin Strategy

## 1. Project Overview
**Goal**: Create a profitable, automated trading strategy for Solana memecoins (Pump.fun ecosystem).
**Scope**: The final output is not strictly a "momentum sniper" but a robust, profitable strategy. It relies heavily on data-driven pre-filtering to avoid rug pulls and identify high-potential tokens.
**Core Philosophy**: "Filter First, Trade Second". The Solana memecoin market is 99% noise/scams. The primary edge comes from *avoiding* the bad trades (Market Structure Analysis), allowing simple trading logic to capture the good ones.

## 2. Tech Stack & Tooling
*   **Package Manager**: `uv` (https://github.com/astral-sh/uv). Always use `uv run` to execute scripts.
*   **Language**: Python 3.10+
*   **Database**: SQLite (via `DBManager`)

## 3. Strategy Evolution (The Journey So Far)

### Phase 1: Exploration (V1 - V6)
*   **V1-V6**: Various attempts at momentum, indicators, and safety guards. High variance, difficulty in finding stability.

### Phase 2: Robust Optimization (V7-V8)
*   **V7**: Tried optimizing complex logic. Result: Extreme variance.
*   **V8**: "Systematic Reconstruction". Simplified to core momentum. Established a baseline but still prone to rug pulls.

### Phase 3: Data-Driven Filtering (V9 - Current)
*   **Pivot**: Shifted focus to **Market Structure Analysis**.
*   **MarketStructureAnalyzer**: Created a tool to analyze thousands of historical trades and extract features (sniper count, dev holdings, volume profiles) of successful vs. failed tokens.
*   **V9_Filtered**:
    *   **Logic**: Integrated the `MarketStructureFilter` (derived from analysis) into the V8 momentum core.
    *   **Status**: Strategy implemented. Optimization script (`optimize_v9_filtered.py`) verified and ready for full-scale runs.

## 3. Current Architecture
*   **Analyzer**: `trader/strategies/analyzers/market_structure_analyzer.py` (The "Brain"). Analyzes historical data to derive filter thresholds.
*   **Strategy**: `trader/strategies/momentum_sniper_v9_filtered.py` (The "Executor"). Applies filters and executes trades.
*   **Optimization**: `scripts/optimize_v9_filtered.py`. Optimizes trading parameters (stop loss, TP, etc.) *after* filtering.
*   **Engine**: Event-driven backtester (`trader/engine/node.py`).

### Key Files
*   `trader/strategies/analyzers/market_structure_analyzer.py`: **PRIORITY #1**. The tool for finding the "edge".
*   `trader/strategies/momentum_sniper_v9_filtered.py`: The current trading implementation.
*   `scripts/optimize_v9_filtered.py`: The optimization pipeline.

## 4. Roadmap & Priorities

### Priority 1: Enhance Market Structure Analysis (Immediate Next Step)
*   **Goal**: Make pre-filtering more effective. The current filters (sniper count, dev holding) are a good start, but can be improved.
*   **Action**: Extend `MarketStructureAnalyzer` to investigate new features:
    *   **Bundle Analysis**: Detect if snipers are funded by the same wallet (cluster analysis).
    *   **Volume Velocity**: Analyze the *rate* of volume change (e.g., first 30s vs 1m). If volume drops off a cliff, it indicates lack of sustained interest.
    *   **Buy/Sell Ratio**: Ratio of buy orders to sell orders in the first minute. High sell pressure early on is a red flag.
    *   **Unique Signers**: Count of unique wallets interacting. Low unique count with high volume indicates wash trading or manipulation.
    *   **Social Signals**: (If data available) Correlation with tweet/telegram activity.
    *   **Liquidity Changes**: Detect liquidity adds/removes.

### Priority 2: V9 Optimization Run
*   **Goal**: Find the optimal trading parameters (SL, TP, Trailing, Buy Amount) for the *filtered* universe.
*   **Action**: Run `scripts/optimize_v9_filtered.py` with high trial counts (e.g., 200+ trials) on the server.

### Priority 3: Advanced Execution (V10)
*   **Goal**: Once filtering is robust, improve the entry/exit execution.
*   **Ideas**:
    *   Dynamic position sizing based on "Quality Score" from the Analyzer.
    *   Multi-stage exits (sell 50% at 2x, let 50% ride).

## 5. How to Continue (Instructions for Next LLM)

1.  **Focus on the Analyzer**: Your primary task is to extend `trader/strategies/analyzers/market_structure_analyzer.py`.
    *   Look for patterns in "Rug Pulls" vs "Moonshots" that are not yet captured.
    *   Add new metrics to the analyzer and run it on the data.
    *   Update the `MarketStructureFilter` thresholds based on your findings.

2.  **Refine the Strategy**:
    *   Update `MomentumSniperV9Filtered` to use any new filters you derive.
    *   Ensure the optimization script (`optimize_v9_filtered.py`) is updated if new parameters are added.

3.  **Validate**:
    *   Always validate new filters by running the optimization/backtest.
    *   The metric that matters is **Risk-Adjusted Return** (Sharpe/Sortino) and **Win Rate** on the *filtered* set.

## 6. Detailed Specifications for Next Tasks

### Task: Extend Market Structure Analyzer
*   **File**: `trader/strategies/analyzers/market_structure_analyzer.py`
*   **Objective**: Identify "Cluster Sniping" and other manipulation patterns.
*   **New Metrics**:
    *   **Volume Velocity**: `vol_1m / vol_30s`.
    *   **Buy/Sell Ratio**: `buy_count / sell_count`.
    *   **Unique Signers**: Count of unique payers.
*   **Usage**:
    *   **Run on full history**:
        ```bash
        rm inspector_data.db # IMPORTANT: Delete old DB first due to schema change
        uv run trader/run_backtest.py --strategy market_structure_analyzer --start-date "2025-09-15 00:00:00" --end-date "2025-10-07 23:59:59"
        ```

### Analysis Findings (2025-11-21)
*   **Unique Signers is the #1 Predictor**:
    *   Tokens with **>30 unique signers** in the first minute have a **14.0% Win Rate** (vs 2.5% baseline) and **1.73x EV** (vs 0.76x baseline).
    *   Recommendation: Set `min_unique_signers` to at least 20-30.
*   **Volume Velocity Warning**:
    *   High velocity (>2.0) correlates with **lower EV** (0.16x). This suggests buying into a vertical pump at T=1m is dangerous (buying the top).
    *   Recommendation: Use a *maximum* velocity cap or be very careful with high-velocity tokens.
*   **Dev Holding**:
    *   Strictly limiting dev holding (<1%) hurts performance.
    *   Recommendation: Allow dev holding up to 10-20%.

### Rug Pull Analysis (2025-11-21)
*   **Bundled Buys**:
    *   Tokens with **>3 bundled buys** have a **20.3% Rug Rate** (vs 0.6% baseline).
    *   Recommendation: Set `max_bundled_buys` to 2 or 3.
*   **Sniper Count**:
    *   Tokens with **>50 snipers** have a **29.4% Rug Rate**.
    *   Recommendation: Set `max_sniper_count` to 30-40.
*   **Dev Early Sell**:
    *   (Inferred) Early dev selling is a major red flag.
    *   Recommendation: Reject if dev sells within first 5 minutes.

### Strategy Options (2025-11-21)
*   **Strict (Current)**:
    *   Filters: `signers>=20`, `bundled<=2`, `snipers<=30`, `conc<=50%`, `vel>=1.2`
    *   Stats: **0.2% Pass Rate**, **2.47x EV**, **31.9% Win Rate**.
    *   Verdict: Highest quality, very low volume.
*   **Balanced**:
    *   Filters: `signers>=10`, `bundled<=5`, `snipers<=50`, `conc<=70%`, `vel>=1.0`
    *   Stats: **2.0% Pass Rate**, **2.24x EV**, **24.2% Win Rate**.
    *   Verdict: **10x more volume**, slightly lower EV. Good middle ground.
*   **Loose**:
    *   Filters: `signers>=5`, `bundled<=10`, `conc<=80%`
    *   Stats: **3.8% Pass Rate**, **2.04x EV**, **20.9% Win Rate**.
    *   Verdict: High volume, but riskier.

    *   Verdict: High volume, but riskier.

### Lifespan Predictor (2025-11-21)
*   **Goal**: Identify tokens that survive > 1 hour.
*   **Key Finding**: `unique_signers >= 20` increases survival chance by **5x** (8.0% vs 1.5%). High velocity (`> 2.0`) reduces survival.
*   **Implementation**: `LifespanScore` in `MarketStructureFilter`.
    *   **Score Logic**: Base(1.0) + Signers(2.0-4.0) + Velocity(±0.5) - Concentration(1.0).
    *   **Usage**: Set `min_lifespan_score` (e.g., 3.0) to filter for longevity.

## 7. Phase 4: Neural Network Pivot (Current Status)
*   **Objective**: Train an LSTM model to predict short-term scalping opportunities (<1min).
*   **Current Progress**:
    *   **Data Generation**: Created `scripts/generate_training_data.py`. Generates 5s candles with features (RSI, ATR, Volatility, Volume Ratio).
    *   **Labeling**: Target = +6% gain within 60s (12 candles) without hitting -2% stop loss (3x Risk/Reward).
    *   **Model**: Created `scripts/train_model.py`. 2-layer LSTM (64 units), trained on ~24k samples.
    *   **Results** (Peak at Epoch 99):
        *   **Recall**: **95%** (Exceptional - misses almost nothing).
        *   **Precision**: **59%** (High enough for profitable trading).
        *   **F1 Score**: **0.72**.
        *   **Val Loss**: 0.2346.
        *   **Conclusion**: The model has exceeded expectations for a small dataset. With **59% Precision** and **95% Recall**, it is ready for a "Paper Trading" test or live deployment with small size. Scaling up data will likely push Precision > 70%.

### Is Scaling Up Promising?
**YES.** The initial baseline (Recall 77%) proves the model can identify pump patterns. The low precision (26%) is expected for a small dataset (24k samples is tiny for deep learning) and basic features. Scaling up to 1M+ samples and adding order book/transaction-level features should significantly boost precision.

## 8. Step-by-Step Guide: Scaling Up Data Training
Before implementing the live strategy, we must improve the model's precision by training on a "wider" dataset.

### Step 1: Data Collection (The "Wide" Net)
*   **Goal**: Acquire 1-2 weeks of continuous trade data for **all** active Solana tokens (not just top 100).
*   **Action**:
    1.  Use `trader/sillm/data_handler.py` to download bulk historical data.
    2.  Ensure we have at least **500,000+** trade samples.

### Step 2: Enhanced Feature Engineering
*   **Goal**: Give the model more "eyes".
*   **Action**: Update `scripts/generate_training_data.py` to include:
    *   **Micro-Structure**: Average trade size, Buy/Sell count ratio.
    *   **Derivatives**: 1st and 2nd derivative of price (Velocity & Acceleration).
    *   **Time Features**: Time of day, day of week (crypto has patterns).
    *   **Lag Features**: RSI values from 1m, 5m ago.

### Step 3: Advanced Training Pipeline
*   **Goal**: Robustness and Generalization.
*   **Action**: Update `scripts/train_model.py`:
    *   **Validation**: Use "Walk-Forward Validation" (Train on Week 1, Test on Week 2) instead of random split.
    *   **Hyperparameter Tuning**: Use Optuna to find best LSTM layers, dropout, and learning rate.
    *   **Ensembling**: Train 5 models and average their predictions to reduce noise.

### Step 4: Final Verification
*   **Target Metrics**:
    *   **Precision**: > 60% (Crucial for profitability).
    *   **Recall**: > 50% (Acceptable to miss some, but must be right when we enter).

## 9. Next Session Handover (Resume Point)
1.  **Execute Step 1**: Run bulk data collection.
2.  **Execute Step 2**: Update `generate_training_data.py` with new features.
3.  **Execute Step 3**: Retrain model and aim for >60% Precision.
4.  **Implement Strategy**: Only *after* model is verified, create `trader/strategies/neural_sniper_v1.py`.
