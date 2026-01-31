import asyncio
import aiohttp
import json
from datetime import datetime

async def fetch_binance_funding(session):
    """Binance USDT-M futures funding rates"""
    url = "https://fapi.binance.com/fapi/v1/premiumIndex"
    async with session.get(url) as resp:
        data = await resp.json()
        return [{"exchange": "binance", "symbol": d["symbol"], "rate": float(d["lastFundingRate"]), "next": d["nextFundingTime"]} for d in data if "USDT" in d["symbol"]]

async def fetch_bybit_funding(session):
    """Bybit linear funding rates"""
    url = "https://api.bybit.com/v5/market/tickers?category=linear"
    async with session.get(url) as resp:
        data = await resp.json()
        result = []
        for d in data.get("result", {}).get("list", []):
            if d.get("fundingRate"):
                result.append({"exchange": "bybit", "symbol": d["symbol"], "rate": float(d["fundingRate"]), "next": d.get("nextFundingTime")})
        return result

async def fetch_hyperliquid_funding(session):
    """Hyperliquid funding rates"""
    url = "https://api.hyperliquid.xyz/info"
    payload = {"type": "metaAndAssetCtxs"}
    async with session.post(url, json=payload) as resp:
        data = await resp.json()
        meta = data[0]["universe"]
        ctxs = data[1]
        result = []
        for i, asset in enumerate(meta):
            if i < len(ctxs):
                rate = float(ctxs[i].get("funding", 0))
                result.append({"exchange": "hyperliquid", "symbol": asset["name"], "rate": rate, "next": None})
        return result

async def fetch_okx_funding(session):
    """OKX swap funding rates"""
    url = "https://www.okx.com/api/v5/public/funding-rate?instType=SWAP"
    async with session.get(url) as resp:
        data = await resp.json()
        return [{"exchange": "okx", "symbol": d["instId"], "rate": float(d["fundingRate"]), "next": d.get("nextFundingTime")} for d in data.get("data", [])]

async def main():
    async with aiohttp.ClientSession() as session:
        results = await asyncio.gather(
            fetch_binance_funding(session),
            fetch_bybit_funding(session),
            fetch_hyperliquid_funding(session),
            fetch_okx_funding(session),
            return_exceptions=True
        )
        
        all_rates = []
        exchanges = ["binance", "bybit", "hyperliquid", "okx"]
        for i, r in enumerate(results):
            if isinstance(r, Exception):
                print(f"Error fetching {exchanges[i]}: {r}")
            else:
                all_rates.extend(r)
        
        # Find most negative funding rates (annualized)
        for r in all_rates:
            r["annualized"] = r["rate"] * 3 * 365 * 100  # 3 funding periods per day
        
        # Sort by most negative
        negative = [r for r in all_rates if r["rate"] < 0]
        negative.sort(key=lambda x: x["rate"])
        
        print(f"\n{'='*60}")
        print(f"FUNDING RATE SCAN - {datetime.utcnow().isoformat()}Z")
        print(f"{'='*60}")
        print(f"\nTotal pairs scanned: {len(all_rates)}")
        print(f"Pairs with negative funding: {len(negative)}")
        
        print(f"\n{'='*60}")
        print("TOP 20 MOST NEGATIVE FUNDING (SHORTS PAY LONGS)")
        print(f"{'='*60}")
        print(f"{'Exchange':<12} {'Symbol':<20} {'Rate':<12} {'Annualized':<12}")
        print("-" * 60)
        for r in negative[:20]:
            print(f"{r['exchange']:<12} {r['symbol']:<20} {r['rate']*100:>10.4f}% {r['annualized']:>10.2f}%")
        
        # Also show positive for comparison
        positive = [r for r in all_rates if r["rate"] > 0]
        positive.sort(key=lambda x: x["rate"], reverse=True)
        
        print(f"\n{'='*60}")
        print("TOP 10 MOST POSITIVE FUNDING (LONGS PAY SHORTS)")
        print(f"{'='*60}")
        for r in positive[:10]:
            print(f"{r['exchange']:<12} {r['symbol']:<20} {r['rate']*100:>10.4f}% {r['annualized']:>10.2f}%")
        
        # Save raw data
        with open("funding_rates.json", "w") as f:
            json.dump(all_rates, f, indent=2)
        
        print(f"\n✓ Saved {len(all_rates)} rates to funding_rates.json")

if __name__ == "__main__":
    asyncio.run(main())
