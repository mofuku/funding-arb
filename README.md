# Funding Rate Arbitrage Bot

Delta-neutral strategy exploiting negative perpetual funding rates.

## Strategy
When funding is negative (shorts pay longs):
1. Long perp on venue with negative funding
2. Short spot (or short perp on another venue)
3. Collect funding payments while delta-neutral
4. Close when funding normalizes

Profit = Σ(funding payments) - entry/exit fees - borrow costs - slippage

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        DATA LAYER                                │
├─────────────────────────────────────────────────────────────────┤
│  Exchange APIs (Binance, Bybit, Hyperliquid, OKX, dYdX)        │
│  └── Funding rates (current + predicted)                        │
│  └── Order books (for slippage estimation)                      │
│  └── Borrow rates (for spot shorting)                           │
│  └── Historical funding (regime detection)                      │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                      SIGNAL LAYER                                │
├─────────────────────────────────────────────────────────────────┤
│  OpportunityScorer                                               │
│  └── Net yield after all costs                                   │
│  └── Funding persistence probability                             │
│  └── Liquidity score                                             │
│  └── Risk-adjusted ranking                                       │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                     EXECUTION LAYER                              │
├─────────────────────────────────────────────────────────────────┤
│  PositionManager                                                 │
│  └── Simultaneous entry (atomic when possible)                   │
│  └── Delta monitoring + rebalancing                              │
│  └── Exit triggers (funding flip, max duration, stop loss)       │
│  └── Slippage-aware order routing                                │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                      RISK LAYER                                  │
├─────────────────────────────────────────────────────────────────┤
│  RiskManager                                                     │
│  └── Position sizing (Kelly-inspired)                            │
│  └── Liquidation buffer monitoring                               │
│  └── Max drawdown enforcement                                    │
│  └── Correlation/regime change detection                         │
└─────────────────────────────────────────────────────────────────┘
```

## Cost Model
- Trading fees: ~0.02-0.05% maker, ~0.04-0.07% taker
- Slippage: depends on size vs liquidity
- Borrow rate: varies by asset (can be 10-50% APR for shorts)
- Funding collection: 3x daily (every 8h)

## Minimum Viable Trade
For a trade to be profitable:
```
8h_funding_rate > (entry_fee + exit_fee + slippage + 8h_borrow_cost) / 2
```

Example:
- Funding: -0.10% per 8h
- Fees: 0.05% entry + 0.05% exit = 0.10%
- Slippage: ~0.05%
- Borrow: 30% APR = 0.01% per 8h

Total cost: 0.16% round trip
Need ~3 funding periods just to break even.

Better targets: Funding < -0.20% with persistence > 24h

## Files
- `fetch_funding.py` - Live funding rate scanner
- `config.py` - Exchange credentials + parameters
- `data/` - Historical funding data
- `models/` - Signal models
- `execution/` - Order execution
- `risk/` - Risk management
- `dashboard/` - Monitoring UI

## Current Market Analysis (2026-01-31)

Last 60 days funding rate data shows calm market conditions:
- **ETH**: -0.014% to +0.01% (never hit -0.05% threshold)
- **SOL**: -0.021% to +0.01% (never hit -0.05% threshold)

**Conclusion**: Strategy requires volatile, directionally-biased markets. 
Monitor is active and will alert when funding gets extreme enough to be profitable.

## Project Structure
```
funding-arb/
├── main.py           # CLI entry point
├── monitor.py        # Continuous funding rate scanner
├── alert_check.py    # Cron-friendly alert checker
├── backtest.py       # Historical backtesting
├── config.py         # Configuration
├── fetch_funding.py  # Raw funding rate fetcher
├── README.md         # This file
├── data/
│   ├── historical/   # Funding rate snapshots
│   └── backtest/     # Cached backtest data
├── models/
│   └── opportunity_scorer.py  # Signal generation
└── execution/
    └── executor.py   # Trade execution engine
```

## Commands
```bash
python3 main.py scan      # One-time opportunity scan
python3 main.py status    # Show bot status
python3 main.py history   # Show historical data
python3 main.py analyze SOL  # Analyze specific asset
python3 backtest.py SOLUSDT ETHUSDT  # Run backtest
python3 monitor.py --interval 300   # Continuous monitoring
```

## Cron Job
Active cron job checks funding every 10 minutes and alerts via main session.
