
## 20251121
after MartKetStructureAnalyzer has been run on historical data you need to be able to draw the consequences. which tokens were successful and how it could be predicted from the near launch data.

think about what other data you needed to successfully identify / flag the token we need to look at vs the ones that are junk.

for example. full volume during the token livecycle, 15m / 1h volume, trade count, ath, holder cnt change, dev sell/buy time, top n token holder percentage, rugg pull signals.

rug pull: if a token looses 90% its price value within 1min - not necessarily from the ath

also you are able to identify the buys which are  in the same transaction with TickData.ts_datetime beeing the same. its useful for identifying bundeled buys - meaning if somebody create a transaction with multiple account buying to hide that they belongs to the same person.


## market filter 20251121
i have a solana meme coin trading backtesting system.
all trials and knew knowledge should be placed into @project_document.md in a structured way for later reference.

i need you to focus on pre-filtering the tokens. there are hundreds / hour 95% dies within couple of minutes.
- create ideas for pre-filtering. be creative. e.g. volume / holder count profile in the early stage
- extend @market_structure_analyzer.py to extract the necessary historical statistics into a db
- create a filter for later strategies like @market_structure_filter.py 



## planning
Create a detailed plan for a profitable solana meme coin strategy implementation.

Ideas: @/docs/knowledge/youtube/latest_knowledge.json 

You have access to a backtesting system, where you might want to create analyzer runs, which will help you to understand the dynamics of the meme coins. These runs might create a statistical result to be used to fine-tune the strategy.

The backtest system can run on ~3month of data but it takes ~10 min each so it might usefull to gradually increase the time interval.

The backtest system base class is in @/trader/engine/strategy_base.py a simple implementation can be found in @/trader/strategies/simple_strategy.py 


You are an expert quantitative crypto trader and strategy engineer. Create a detailed, step-by-step plan for designing, implementing, and validating a profitable Solana meme coin trading strategy.

## Context:

Knowledge: @/docs/knowledge/youtube/latest_knowledge.json (contains recent insights on meme coin dynamics).

## Codebase:

Base class for strategies: @/trader/engine/strategy_base.py

Example implementation: @/trader/strategies/simple_strategy.py

## Backtesting System:

Uses ~3 months of meme coin launch/trade data.

Each run takes ~10 minutes.

Recommended approach: start with shorter intervals, then expand to longer intervals for statistical significance.

Backtests generate analyzer outputs with statistical summaries, which can be used to fine-tune the strategy.

## Requirements for the Plan:

### Research Phase

Summarize key insights from the latest knowledge JSON about meme coin behavior.

Define initial hypotheses for profitable trading patterns.

Specify risk constraints (e.g., position sizing, stop-loss rules).

### Implementation Phase

Define the technical structure of the new strategy class, extending strategy_base.py.

Identify what modifications are needed compared to simple_strategy.py.

List the indicators, signals, and conditions required for entries and exits.

### Backtesting & Validation Phase

Design an incremental backtest plan (e.g., 1 week → 1 month → 3 months).

Define key performance metrics (PnL, Sharpe ratio, drawdown, win rate).

Suggest how to automate multiple backtest runs to save time.

### Optimization Phase

Propose how to use statistical outputs from analyzers to adjust parameters.

Define a process for avoiding overfitting while improving performance.

### Deployment Plan

Outline steps for moving from backtest to paper trading (dry-run) to live trading.

Specify monitoring requirements and alerting for anomalies.

Deliverables

Clear timeline of steps (with dependencies).

List of artifacts to be produced (code modules, configs, logs, statistical reports).

Output Format:
Provide the plan as a structured document with numbered sections, sub-steps, and reasoning for each choice. Include practical details so an engineer could start coding right away.