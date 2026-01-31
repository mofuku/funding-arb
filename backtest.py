#!/usr/bin/env python3
"""
Backtesting engine for funding rate arbitrage.
Downloads historical funding data and simulates strategy performance.
"""
import asyncio
import aiohttp
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from dataclasses import dataclass
import pandas as pd

DATA_DIR = Path("data/backtest")
DATA_DIR.mkdir(parents=True, exist_ok=True)

@dataclass
class BacktestConfig:
    # Entry threshold (funding rate per 8h)
    entry_threshold: float = -0.0015  # -0.15%
    exit_threshold: float = -0.0005   # -0.05% (close when funding normalizes)
    
    # Costs
    entry_cost: float = 0.001   # 0.1% (taker both legs)
    exit_cost: float = 0.0004   # 0.04% (maker both legs)
    slippage: float = 0.001     # 0.1% round trip
    borrow_rate_8h: float = 0.000274  # 30% APR
    
    # Position sizing
    position_size: float = 1000  # $1000 per position
    max_positions: int = 3

async def fetch_binance_funding_history(symbol: str, days: int = 30) -> list[dict]:
    """Fetch historical funding rates from Binance"""
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

def run_backtest(funding_data: list[dict], config: BacktestConfig) -> dict:
    """
    Run backtest simulation.
    
    Returns performance metrics.
    """
    if not funding_data:
        return {"error": "No data"}
    
    # Convert to DataFrame
    df = pd.DataFrame(funding_data)
    df["fundingRate"] = df["fundingRate"].astype(float)
    df["timestamp"] = pd.to_datetime(df["fundingTime"], unit="ms")
    df = df.sort_values("timestamp").reset_index(drop=True)
    
    # Simulation state
    position_open = False
    entry_rate = 0
    entry_idx = 0
    trades = []
    total_pnl = 0
    total_funding = 0
    total_costs = 0
    
    for i, row in df.iterrows():
        rate = row["fundingRate"]
        
        if not position_open:
            # Check entry
            if rate < config.entry_threshold:
                position_open = True
                entry_rate = rate
                entry_idx = i
                total_costs += (config.entry_cost + config.slippage) * config.position_size
        else:
            # Collect funding
            funding_received = -rate * config.position_size
            total_funding += funding_received
            total_costs += config.borrow_rate_8h * config.position_size
            
            # Check exit
            if rate > config.exit_threshold:
                position_open = False
                total_costs += config.exit_cost * config.position_size
                
                periods = i - entry_idx
                trade_funding = sum(-df.iloc[j]["fundingRate"] * config.position_size 
                                   for j in range(entry_idx, i+1))
                trade_costs = ((config.entry_cost + config.exit_cost + config.slippage) * config.position_size +
                              config.borrow_rate_8h * config.position_size * periods)
                trade_pnl = trade_funding - trade_costs
                
                trades.append({
                    "entry_time": df.iloc[entry_idx]["timestamp"],
                    "exit_time": row["timestamp"],
                    "periods": periods,
                    "avg_funding": entry_rate,
                    "funding_collected": trade_funding,
                    "costs": trade_costs,
                    "pnl": trade_pnl,
                    "pnl_pct": trade_pnl / config.position_size * 100,
                })
                total_pnl += trade_pnl
    
    # Calculate metrics
    days = (df["timestamp"].iloc[-1] - df["timestamp"].iloc[0]).days or 1
    
    return {
        "symbol": funding_data[0].get("symbol", "unknown"),
        "period_days": days,
        "data_points": len(df),
        "total_trades": len(trades),
        "total_funding": total_funding,
        "total_costs": total_costs,
        "total_pnl": total_pnl,
        "pnl_per_trade": total_pnl / len(trades) if trades else 0,
        "win_rate": sum(1 for t in trades if t["pnl"] > 0) / len(trades) * 100 if trades else 0,
        "avg_hold_periods": sum(t["periods"] for t in trades) / len(trades) if trades else 0,
        "annualized_return": (total_pnl / config.position_size) * (365 / days) * 100 if days else 0,
        "trades": trades[-10:],  # Last 10 trades
    }

async def main(symbols: list[str], days: int = 30):
    print(f"\n{'='*70}")
    print(f"FUNDING RATE BACKTEST - Last {days} days")
    print(f"{'='*70}")
    
    config = BacktestConfig()
    print(f"\nConfig:")
    print(f"  Entry: funding < {config.entry_threshold*100:.2f}%")
    print(f"  Exit: funding > {config.exit_threshold*100:.2f}%")
    print(f"  Position size: ${config.position_size}")
    
    for symbol in symbols:
        print(f"\n{'='*50}")
        print(f"Fetching {symbol}...")
        
        # Check cache
        cache_file = DATA_DIR / f"{symbol}_{days}d.json"
        if cache_file.exists():
            with open(cache_file) as f:
                data = json.load(f)
            print(f"  Loaded from cache ({len(data)} records)")
        else:
            data = await fetch_binance_funding_history(symbol, days)
            with open(cache_file, "w") as f:
                json.dump(data, f)
            print(f"  Fetched {len(data)} records")
        
        if not data:
            print(f"  No data for {symbol}")
            continue
        
        results = run_backtest(data, config)
        
        print(f"\n📊 {symbol} Results:")
        print(f"  Period: {results['period_days']} days")
        print(f"  Total trades: {results['total_trades']}")
        print(f"  Win rate: {results['win_rate']:.1f}%")
        print(f"  Avg hold: {results['avg_hold_periods']:.1f} periods ({results['avg_hold_periods']*8:.0f}h)")
        print(f"  Total P&L: ${results['total_pnl']:.2f}")
        print(f"  Annualized: {results['annualized_return']:.1f}%")
        
        if results['trades']:
            print(f"\n  Recent trades:")
            for t in results['trades'][-3:]:
                print(f"    {t['entry_time'].strftime('%m/%d')} → {t['exit_time'].strftime('%m/%d')}: "
                      f"${t['pnl']:.2f} ({t['pnl_pct']:.2f}%)")

if __name__ == "__main__":
    import sys
    symbols = sys.argv[1:] if len(sys.argv) > 1 else ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
    asyncio.run(main(symbols, days=60))
