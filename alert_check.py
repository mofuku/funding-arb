#!/usr/bin/env python3
"""
Alert check for cron - outputs alert text if opportunities found.
Run this from OpenClaw cron to get notified of funding opportunities.
"""
import asyncio
import sys
from monitor import fetch_all_funding, find_opportunities

async def main():
    try:
        rates = await fetch_all_funding()
        opportunities = find_opportunities(rates)
        
        if opportunities:
            # Output alert for cron to pick up
            print(f"🚨 **FUNDING ARB ALERT** - {len(opportunities)} opportunities!")
            print()
            for opp in opportunities[:5]:
                print(f"• **{opp['base']}** @ {opp['exchange']}")
                print(f"  Funding: {opp['annualized']:.1f}% → Net: {opp['net_yield_apr']:.1f}% APR")
            print()
            print("Run `cd ~/dev/funding-arb && python3 main.py scan` for details")
            sys.exit(0)  # Alert found
        else:
            # No alert needed
            sys.exit(1)  # Silent exit
    except Exception as e:
        print(f"Error checking funding: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())
