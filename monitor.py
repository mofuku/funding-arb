#!/usr/bin/env python3
"""
Funding rate monitoring daemon.
Continuously scans for opportunities and saves historical data.
"""
import asyncio
import aiohttp
import json
import os
from datetime import datetime, timezone
from pathlib import Path
import sys

# Ensure data directory exists
DATA_DIR = Path("data/historical")
DATA_DIR.mkdir(parents=True, exist_ok=True)

# Alert thresholds
ALERT_FUNDING_THRESHOLD = -0.0015  # -0.15% per 8h (annualized ~-164%)
MIN_NET_YIELD_APR = 30  # Alert if net yield > 30%

# Cost assumptions for quick calc
ROUND_TRIP_COST = 0.0024  # ~0.24% (entry + exit + slippage)
BORROW_8H = 0.000274  # ~30% APR

WHITELIST = {
    "BTC", "ETH", "SOL", "DOGE", "XRP", "ADA", "AVAX", "LINK", 
    "DOT", "MATIC", "UNI", "ATOM", "LTC", "BCH", "APT", "ARB",
    "OP", "INJ", "SUI", "SEI", "TIA", "JUP", "PYTH", "JTO",
    "WIF", "BONK", "PEPE", "SHIB", "FIL", "NEAR", "RENDER"
}

def extract_base(symbol: str) -> str:
    for suffix in ["USDT", "USD", "PERP", "-USDT-SWAP", "-USD-SWAP"]:
        if symbol.endswith(suffix):
            return symbol[:-len(suffix)]
    return symbol

async def fetch_all_funding() -> list[dict]:
    """Fetch funding rates from all exchanges"""
    async with aiohttp.ClientSession() as session:
        tasks = [
            fetch_binance(session),
            fetch_bybit(session),
            fetch_hyperliquid(session),
            fetch_okx(session),
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        all_rates = []
        for r in results:
            if isinstance(r, list):
                all_rates.extend(r)
        return all_rates

async def fetch_binance(session):
    url = "https://fapi.binance.com/fapi/v1/premiumIndex"
    async with session.get(url, timeout=10) as resp:
        data = await resp.json()
        return [{"exchange": "binance", "symbol": d["symbol"], "rate": float(d["lastFundingRate"])} 
                for d in data if "USDT" in d["symbol"]]

async def fetch_bybit(session):
    url = "https://api.bybit.com/v5/market/tickers?category=linear"
    async with session.get(url, timeout=10) as resp:
        data = await resp.json()
        return [{"exchange": "bybit", "symbol": d["symbol"], "rate": float(d.get("fundingRate", 0))} 
                for d in data.get("result", {}).get("list", []) if d.get("fundingRate")]

async def fetch_hyperliquid(session):
    url = "https://api.hyperliquid.xyz/info"
    async with session.post(url, json={"type": "metaAndAssetCtxs"}, timeout=10) as resp:
        data = await resp.json()
        meta, ctxs = data[0]["universe"], data[1]
        return [{"exchange": "hyperliquid", "symbol": meta[i]["name"], "rate": float(ctxs[i].get("funding", 0))}
                for i in range(min(len(meta), len(ctxs)))]

async def fetch_okx(session):
    url = "https://www.okx.com/api/v5/public/funding-rate?instType=SWAP"
    async with session.get(url, timeout=10) as resp:
        data = await resp.json()
        return [{"exchange": "okx", "symbol": d["instId"], "rate": float(d["fundingRate"])} 
                for d in data.get("data", [])]

def calculate_net_yield(funding_rate: float) -> float:
    """Calculate net yield APR after costs, assuming 24h hold (3 periods)"""
    if funding_rate >= 0:
        return 0
    funding_received = -funding_rate
    amortized_cost = ROUND_TRIP_COST / 3
    net_8h = funding_received - BORROW_8H - amortized_cost
    return net_8h * 3 * 365 * 100

def find_opportunities(rates: list[dict]) -> list[dict]:
    """Find actionable opportunities"""
    opps = []
    for r in rates:
        base = extract_base(r["symbol"])
        if base not in WHITELIST:
            continue
        if r["rate"] >= ALERT_FUNDING_THRESHOLD:
            continue
        
        net_yield = calculate_net_yield(r["rate"])
        if net_yield >= MIN_NET_YIELD_APR:
            opps.append({
                **r,
                "base": base,
                "annualized": r["rate"] * 3 * 365 * 100,
                "net_yield_apr": net_yield,
            })
    
    return sorted(opps, key=lambda x: x["net_yield_apr"], reverse=True)

def save_snapshot(rates: list[dict], opportunities: list[dict]):
    """Save rates snapshot to historical data"""
    now = datetime.now(timezone.utc)
    date_str = now.strftime("%Y-%m-%d")
    time_str = now.strftime("%H%M")
    
    # Save full snapshot
    snapshot_file = DATA_DIR / f"{date_str}.jsonl"
    with open(snapshot_file, "a") as f:
        record = {
            "ts": now.isoformat(),
            "rates_count": len(rates),
            "opp_count": len(opportunities),
            "top_opps": opportunities[:5],
        }
        f.write(json.dumps(record) + "\n")
    
    return snapshot_file

def format_alert(opportunities: list[dict]) -> str:
    """Format alert message"""
    lines = ["🚨 **FUNDING ARB OPPORTUNITIES DETECTED**\n"]
    for opp in opportunities[:5]:
        lines.append(
            f"• **{opp['base']}** @ {opp['exchange']}: "
            f"funding {opp['annualized']:.1f}% → net {opp['net_yield_apr']:.1f}% APR"
        )
    return "\n".join(lines)

async def run_scan():
    """Single scan iteration"""
    try:
        rates = await fetch_all_funding()
        opportunities = find_opportunities(rates)
        save_snapshot(rates, opportunities)
        
        timestamp = datetime.now(timezone.utc).strftime("%H:%M:%S")
        
        if opportunities:
            print(f"\n[{timestamp}] 🎯 FOUND {len(opportunities)} OPPORTUNITIES!")
            print(format_alert(opportunities))
            # Could trigger notification here
            return opportunities
        else:
            # Find best even if below threshold
            whitelisted = [r for r in rates if extract_base(r["symbol"]) in WHITELIST and r["rate"] < 0]
            if whitelisted:
                best = min(whitelisted, key=lambda x: x["rate"])
                net = calculate_net_yield(best["rate"])
                print(f"[{timestamp}] No opps. Best: {best['symbol']} @ {best['rate']*100:.4f}% (net {net:.1f}% APR) - need < {ALERT_FUNDING_THRESHOLD*100:.2f}%")
            else:
                print(f"[{timestamp}] No negative funding on whitelisted assets")
            return []
    except Exception as e:
        print(f"[ERROR] Scan failed: {e}")
        return []

async def monitor_loop(interval_seconds: int = 300):
    """Continuous monitoring loop"""
    print(f"Starting funding rate monitor...")
    print(f"Alert threshold: funding < {ALERT_FUNDING_THRESHOLD*100:.2f}%, net yield > {MIN_NET_YIELD_APR}% APR")
    print(f"Scan interval: {interval_seconds}s")
    print(f"Watching {len(WHITELIST)} assets\n")
    
    while True:
        await run_scan()
        await asyncio.sleep(interval_seconds)

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true", help="Run single scan")
    parser.add_argument("--interval", type=int, default=300, help="Scan interval (seconds)")
    args = parser.parse_args()
    
    if args.once:
        asyncio.run(run_scan())
    else:
        asyncio.run(monitor_loop(args.interval))
