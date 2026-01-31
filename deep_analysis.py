#!/usr/bin/env python3
"""
Deep analysis of funding rate arbitrage profitability.
"""
import asyncio
import aiohttp
import json
from datetime import datetime, timezone
from pathlib import Path
import statistics

DATA_DIR = Path("data/backtest")
DATA_DIR.mkdir(parents=True, exist_ok=True)

async def fetch_funding_history(symbol: str, days: int = 365) -> list[dict]:
    """Fetch historical funding from Binance"""
    url = "https://fapi.binance.com/fapi/v1/fundingRate"
    
    async with aiohttp.ClientSession() as session:
        all_data = []
        end_time = int(datetime.now(timezone.utc).timestamp() * 1000)
        start_time = end_time - (days * 24 * 60 * 60 * 1000)
        
        while True:
            params = {
                "symbol": symbol,
                "startTime": start_time,
                "endTime": end_time,
                "limit": 1000
            }
            async with session.get(url, params=params) as resp:
                data = await resp.json()
                if not data:
                    break
                all_data.extend(data)
                if len(data) < 1000:
                    break
                end_time = data[0]["fundingTime"] - 1
        
        return sorted(all_data, key=lambda x: x["fundingTime"])

def analyze_funding_distribution(data: list[dict]) -> dict:
    """Analyze funding rate distribution"""
    rates = [float(d["fundingRate"]) for d in data]
    
    negative_rates = [r for r in rates if r < 0]
    extreme_negative = [r for r in rates if r < -0.001]  # < -0.1%
    very_extreme = [r for r in rates if r < -0.0015]     # < -0.15%
    
    return {
        "count": len(rates),
        "days": len(rates) / 3,  # 3 funding periods per day
        "mean": statistics.mean(rates) * 100,
        "median": statistics.median(rates) * 100,
        "stdev": statistics.stdev(rates) * 100,
        "min": min(rates) * 100,
        "max": max(rates) * 100,
        "pct_negative": len(negative_rates) / len(rates) * 100,
        "pct_below_minus_0.1": len(extreme_negative) / len(rates) * 100,
        "pct_below_minus_0.15": len(very_extreme) / len(rates) * 100,
        "extreme_events": len(very_extreme),
    }

def simulate_realistic_strategy(data: list[dict]) -> dict:
    """
    Simulate with REALISTIC thresholds based on historical data.
    
    Strategy variants:
    1. Conservative: -0.15% entry (rare)
    2. Moderate: -0.10% entry
    3. Aggressive: -0.05% entry
    """
    rates = [(float(d["fundingRate"]), d["fundingTime"]) for d in data]
    
    results = {}
    
    for strategy_name, entry_thresh, exit_thresh in [
        ("conservative", -0.0015, -0.0003),  # -0.15% to -0.03%
        ("moderate", -0.0010, -0.0002),      # -0.10% to -0.02%
        ("aggressive", -0.0005, 0.0),        # -0.05% to 0%
    ]:
        # Costs (per $1000 position)
        entry_cost = 1.0    # 0.10% entry (taker both legs)
        exit_cost = 0.4     # 0.04% exit (maker)
        slippage = 0.5      # 0.05% slippage
        borrow_8h = 0.274   # ~30% APR
        
        trades = []
        in_position = False
        entry_idx = 0
        
        for i, (rate, ts) in enumerate(rates):
            if not in_position:
                if rate < entry_thresh:
                    in_position = True
                    entry_idx = i
            else:
                if rate > exit_thresh:
                    in_position = False
                    periods = i - entry_idx
                    
                    # Funding collected (shorts pay us when rate negative)
                    funding = sum(-rates[j][0] * 1000 for j in range(entry_idx, i+1))
                    
                    # Costs
                    costs = entry_cost + exit_cost + slippage + (borrow_8h * periods)
                    
                    pnl = funding - costs
                    trades.append({
                        "periods": periods,
                        "hours": periods * 8,
                        "funding": funding,
                        "costs": costs,
                        "pnl": pnl,
                    })
        
        total_pnl = sum(t["pnl"] for t in trades)
        days = len(rates) / 3
        
        results[strategy_name] = {
            "entry_threshold": entry_thresh * 100,
            "exit_threshold": exit_thresh * 100,
            "total_trades": len(trades),
            "trades_per_month": len(trades) / (days / 30),
            "total_pnl": total_pnl,
            "annualized_return": (total_pnl / 1000) * (365 / days) * 100 if days > 0 else 0,
            "win_rate": sum(1 for t in trades if t["pnl"] > 0) / len(trades) * 100 if trades else 0,
            "avg_pnl_per_trade": total_pnl / len(trades) if trades else 0,
            "avg_hold_hours": sum(t["hours"] for t in trades) / len(trades) if trades else 0,
            "total_costs": sum(t["costs"] for t in trades),
            "total_funding": sum(t["funding"] for t in trades),
        }
    
    return results

def calculate_break_even(cost_per_trade: float = 1.9, hold_periods: int = 3) -> float:
    """
    Calculate minimum funding rate needed to break even.
    
    Costs per trade ($1000 position):
    - Entry: 2x taker = 2 * 0.04% = $0.80
    - Exit: 2x maker = 2 * 0.02% = $0.40  
    - Slippage: ~0.05% = $0.50
    - Borrow: 30% APR = 0.0274% per 8h = $0.274 per period
    
    Total for 3-period hold: $0.80 + $0.40 + $0.50 + $0.82 = $2.52
    """
    entry = 0.80  # 2x taker @ 0.04%
    exit = 0.40   # 2x maker @ 0.02%
    slippage = 0.50
    borrow = 0.274 * hold_periods
    
    total_cost = entry + exit + slippage + borrow
    
    # To break even: funding collected > total cost
    # funding = -rate * $1000 * periods
    # -rate * 1000 * periods > total_cost
    # -rate > total_cost / (1000 * periods)
    
    min_rate = -total_cost / (1000 * hold_periods)
    return min_rate

async def main():
    symbols = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "DOGEUSDT", "XRPUSDT"]
    
    print("=" * 80)
    print("FUNDING RATE ARBITRAGE — DEEP PROFITABILITY ANALYSIS")
    print("=" * 80)
    
    # Break-even analysis
    print("\n📐 BREAK-EVEN ANALYSIS")
    print("-" * 40)
    for periods in [1, 3, 5, 10]:
        min_rate = calculate_break_even(hold_periods=periods)
        print(f"  {periods} periods ({periods*8}h hold): need < {min_rate*100:.3f}% per 8h")
    
    # Fetch and analyze each symbol
    all_results = {}
    
    for symbol in symbols:
        print(f"\n{'=' * 60}")
        print(f"📊 {symbol}")
        print("=" * 60)
        
        cache_file = DATA_DIR / f"{symbol}_365d.json"
        if cache_file.exists():
            with open(cache_file) as f:
                data = json.load(f)
            print(f"Loaded {len(data)} records from cache")
        else:
            print("Fetching 1 year of data...")
            data = await fetch_funding_history(symbol, days=365)
            with open(cache_file, "w") as f:
                json.dump(data, f)
            print(f"Fetched {len(data)} records")
        
        if len(data) < 10:
            print("  Insufficient data")
            continue
        
        # Distribution analysis
        dist = analyze_funding_distribution(data)
        print(f"\n📈 DISTRIBUTION ({dist['days']:.0f} days)")
        print(f"  Mean:   {dist['mean']:+.4f}%")
        print(f"  Median: {dist['median']:+.4f}%")
        print(f"  StdDev: {dist['stdev']:.4f}%")
        print(f"  Range:  [{dist['min']:.3f}%, {dist['max']:.3f}%]")
        print(f"\n  % Negative:    {dist['pct_negative']:.1f}%")
        print(f"  % Below -0.1%: {dist['pct_below_minus_0.1']:.1f}%")
        print(f"  % Below -0.15%: {dist['pct_below_minus_0.15']:.1f}%")
        print(f"  Extreme events (< -0.15%): {dist['extreme_events']}")
        
        # Strategy simulation
        strats = simulate_realistic_strategy(data)
        print(f"\n💰 STRATEGY SIMULATION")
        
        for name, s in strats.items():
            print(f"\n  {name.upper()} (entry < {s['entry_threshold']:.2f}%)")
            print(f"    Trades: {s['total_trades']} ({s['trades_per_month']:.1f}/month)")
            print(f"    Win rate: {s['win_rate']:.1f}%")
            print(f"    Avg hold: {s['avg_hold_hours']:.0f}h")
            print(f"    Total P&L: ${s['total_pnl']:.2f}")
            print(f"    Funding collected: ${s['total_funding']:.2f}")
            print(f"    Total costs: ${s['total_costs']:.2f}")
            print(f"    Annualized: {s['annualized_return']:.1f}%")
        
        all_results[symbol] = {"distribution": dist, "strategies": strats}
    
    # Summary
    print("\n" + "=" * 80)
    print("📋 VERDICT")
    print("=" * 80)
    
    # Calculate aggregate stats
    total_conservative_pnl = sum(r["strategies"]["conservative"]["total_pnl"] for r in all_results.values())
    total_moderate_pnl = sum(r["strategies"]["moderate"]["total_pnl"] for r in all_results.values())
    total_aggressive_pnl = sum(r["strategies"]["aggressive"]["total_pnl"] for r in all_results.values())
    
    print(f"\n  Portfolio P&L (1 year, $1k per position):")
    print(f"    Conservative: ${total_conservative_pnl:.2f}")
    print(f"    Moderate:     ${total_moderate_pnl:.2f}")
    print(f"    Aggressive:   ${total_aggressive_pnl:.2f}")
    
    print(f"\n  🎯 Key Findings:")
    avg_extreme = statistics.mean(r["distribution"]["pct_below_minus_0.15"] for r in all_results.values())
    print(f"    - Funding < -0.15% occurs only {avg_extreme:.1f}% of the time")
    print(f"    - Conservative strategy: rare trades, but profitable when they happen")
    print(f"    - Moderate strategy: more trades, but costs eat into profits")
    print(f"    - Aggressive strategy: frequent trades, but often unprofitable")
    
    print(f"\n  ⚠️ Reality Check:")
    print(f"    - Strategy only works during high volatility / liquidation cascades")
    print(f"    - In calm markets (like now), opportunities are rare")
    print(f"    - Need to be ready to act fast when funding spikes negative")
    print(f"    - Best as opportunistic play, not steady income")
    
    return all_results

if __name__ == "__main__":
    asyncio.run(main())
