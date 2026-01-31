#!/usr/bin/env python3
"""
Funding Rate Arbitrage Bot - Main Entry Point

Commands:
  scan      - One-time scan for opportunities
  monitor   - Continuous monitoring with alerts
  backtest  - Run historical backtest
  status    - Show current positions and stats
  execute   - Execute a trade (requires API keys)
"""
import asyncio
import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from config import load_config
from monitor import run_scan, find_opportunities, fetch_all_funding, calculate_net_yield, WHITELIST, extract_base
from models.opportunity_scorer import OpportunityScorer

def cmd_scan(args):
    """Run single scan and display opportunities"""
    print(f"\n{'='*70}")
    print(f"FUNDING RATE SCANNER - {datetime.now(timezone.utc).isoformat()}")
    print(f"{'='*70}\n")
    
    asyncio.run(run_scan())

def cmd_status(args):
    """Show system status"""
    config = load_config()
    data_dir = Path("data/historical")
    
    print(f"\n{'='*50}")
    print("FUNDING ARB BOT STATUS")
    print(f"{'='*50}")
    
    # Config
    print(f"\nConfiguration:")
    print(f"  Min net yield: {config.trading.min_net_yield_pct}% APR")
    print(f"  Max position: ${config.trading.max_position_usd}")
    print(f"  Max concurrent: {config.trading.max_positions}")
    print(f"  Whitelisted assets: {len(config.symbol_whitelist)}")
    
    # Historical data
    if data_dir.exists():
        files = list(data_dir.glob("*.jsonl"))
        total_lines = sum(1 for f in files for _ in open(f))
        print(f"\nHistorical data:")
        print(f"  Days tracked: {len(files)}")
        print(f"  Total snapshots: {total_lines}")
    
    # Active positions (placeholder)
    print(f"\nActive positions: 0")
    print(f"Total P&L: $0.00")

def cmd_history(args):
    """Show historical funding data"""
    data_dir = Path("data/historical")
    if not data_dir.exists():
        print("No historical data found. Run 'scan' first.")
        return
    
    # Load recent data
    files = sorted(data_dir.glob("*.jsonl"), reverse=True)[:7]
    
    print(f"\n{'='*60}")
    print("RECENT FUNDING HISTORY")
    print(f"{'='*60}")
    
    opp_counts = []
    for f in files:
        with open(f) as fp:
            records = [json.loads(line) for line in fp]
        
        opps = sum(r["opp_count"] for r in records)
        opp_counts.append((f.stem, len(records), opps))
    
    print(f"\n{'Date':<12} {'Scans':<8} {'Opportunities':<15}")
    print("-" * 40)
    for date, scans, opps in opp_counts:
        print(f"{date:<12} {scans:<8} {opps:<15}")

def cmd_analyze(args):
    """Analyze a specific asset's funding history"""
    rates = asyncio.run(fetch_all_funding())
    asset = args.asset.upper()
    
    asset_rates = [r for r in rates if extract_base(r["symbol"]) == asset]
    if not asset_rates:
        print(f"No data found for {asset}")
        return
    
    print(f"\n{'='*60}")
    print(f"FUNDING ANALYSIS: {asset}")
    print(f"{'='*60}")
    
    for r in sorted(asset_rates, key=lambda x: x["rate"]):
        net = calculate_net_yield(r["rate"])
        status = "✅ ACTIONABLE" if net > 30 else "❌ costs > yield" if r["rate"] < 0 else "neutral"
        print(f"{r['exchange']:<12} {r['symbol']:<18} {r['rate']*100:>8.4f}% (net {net:>6.1f}% APR) {status}")

def main():
    parser = argparse.ArgumentParser(description="Funding Rate Arbitrage Bot")
    subparsers = parser.add_subparsers(dest="command", help="Commands")
    
    # Scan
    scan_parser = subparsers.add_parser("scan", help="One-time opportunity scan")
    scan_parser.set_defaults(func=cmd_scan)
    
    # Status
    status_parser = subparsers.add_parser("status", help="Show bot status")
    status_parser.set_defaults(func=cmd_status)
    
    # History
    hist_parser = subparsers.add_parser("history", help="Show funding history")
    hist_parser.set_defaults(func=cmd_history)
    
    # Analyze
    analyze_parser = subparsers.add_parser("analyze", help="Analyze specific asset")
    analyze_parser.add_argument("asset", help="Asset symbol (e.g., SOL, ETH)")
    analyze_parser.set_defaults(func=cmd_analyze)
    
    args = parser.parse_args()
    
    if args.command:
        args.func(args)
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
