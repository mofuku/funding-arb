# Funding Rate Arbitrage — Profitability Report

**Date:** 2026-01-31  
**Data:** 1 year of Binance funding history (BTC, ETH, SOL, DOGE, XRP + volatile alts)

## TL;DR

**The strategy is not profitable for steady income.**

In the past year:
- Only **3 tradeable events** across all major assets
- Total P&L: **$6.73** on $1,000 positions
- Annualized return: **<1%**

## The Math Problem

### Break-Even Requirements

| Hold Period | Min Funding Rate |
|-------------|------------------|
| 8h (1 period) | **-0.197%** |
| 24h (3 periods) | **-0.084%** |
| 40h (5 periods) | **-0.061%** |
| 80h (10 periods) | **-0.044%** |

### Cost Breakdown (per $1,000 position)

```
Entry:    $0.80  (2x taker @ 0.04%)
Exit:     $0.40  (2x maker @ 0.02%)
Slippage: $0.50  (0.05%)
Borrow:   $0.27/period (30% APR)
─────────────────────────────
Total:    $1.70 + $0.27/period
```

To break even on a 24h trade: need -0.084% funding sustained.

### Historical Reality

| Asset | Min Funding | Max Funding | % Below -0.1% |
|-------|-------------|-------------|---------------|
| BTC | -0.012% | +0.010% | **0.0%** |
| ETH | -0.025% | +0.010% | **0.0%** |
| SOL | -0.303% | +0.026% | **0.5%** |
| DOGE | -0.024% | +0.045% | **0.0%** |
| XRP | -0.033% | +0.044% | **0.0%** |

**Only SOL hit the threshold — 3 times in a year.**

## Why The Strategy Fails

1. **Fees eat everything.** Even at VIP tier fees, round-trip costs ~0.14% before borrow. Funding rarely exceeds this.

2. **Negative funding is rare.** Market is structurally long-biased. Shorts pay longs 85%+ of the time.

3. **When it happens, it's brief.** Extreme funding normalizes within 1-3 periods. Not enough time to cover costs.

4. **Borrow rates compound.** 30% APR = 0.027% per 8h. This erodes any edge on longer holds.

## When It Could Work

The strategy only makes sense during:
- **Liquidation cascades** (March 2020, May 2021, June 2022)
- **Black swan events** with sustained panic
- **Specific altcoins** during token-specific disasters

These are rare, unpredictable, and require immediate execution.

## Verdict

| Use Case | Verdict |
|----------|---------|
| Steady income | ❌ No |
| Passive strategy | ❌ No |
| Opportunistic (crisis-only) | ⚠️ Maybe |
| On Hyperliquid (lower fees) | ⚠️ Research needed |

**Recommendation:** Archive the bot. Keep the monitoring code for alerts during market crashes. Don't allocate capital to this strategy for passive returns.

## What Actually Works For Yield

If you want delta-neutral yield, consider:
- **Basis trade** (spot long + quarterly short) — predictable, ~10-20% APR
- **LP on stables** — Curve, Uniswap stables — ~5-15% APR
- **Lending protocols** — Aave, Compound — ~3-8% APR
- **Ethena** (if you trust the mechanism) — variable

These have better risk/reward than funding arb in normal markets.

---

*Analysis by Milos • Data source: Binance Futures API*
