"""
Opportunity scoring for funding rate arbitrage.
Calculates net yield after all costs and ranks opportunities.
"""
import json
from dataclasses import dataclass
from typing import Optional
from datetime import datetime
import sys
sys.path.append("..")
from config import load_config, Config

@dataclass
class Opportunity:
    exchange: str
    symbol: str
    base_asset: str
    funding_rate: float  # Per 8h period
    funding_annualized: float  # APR
    
    # Cost estimates
    entry_cost: float
    exit_cost: float
    slippage_cost: float
    borrow_cost_8h: float
    
    # Net yield
    net_yield_8h: float
    net_yield_annualized: float
    
    # Metadata
    liquidity_score: float  # 0-1
    timestamp: str
    
    def to_dict(self):
        return self.__dict__

class OpportunityScorer:
    def __init__(self, config: Config):
        self.config = config
        self.costs = config.costs
        self.trading = config.trading
        
    def get_fees(self, exchange: str) -> tuple[float, float]:
        """Get maker/taker fees for exchange"""
        fee_map = {
            "binance": (self.costs.binance_maker, self.costs.binance_taker),
            "bybit": (self.costs.bybit_maker, self.costs.bybit_taker),
            "hyperliquid": (self.costs.hyperliquid_maker, self.costs.hyperliquid_taker),
            "okx": (self.costs.okx_maker, self.costs.okx_taker),
        }
        return fee_map.get(exchange, (0.0005, 0.0005))
    
    def extract_base_asset(self, symbol: str) -> str:
        """Extract base asset from symbol (BTCUSDT -> BTC)"""
        suffixes = ["USDT", "USD", "PERP", "-USDT-SWAP", "-USD-SWAP"]
        for suffix in suffixes:
            if symbol.endswith(suffix):
                return symbol[:-len(suffix)]
        return symbol
    
    def is_whitelisted(self, symbol: str) -> bool:
        """Check if symbol's base asset is in whitelist"""
        base = self.extract_base_asset(symbol)
        return base in self.config.symbol_whitelist
    
    def calculate_opportunity(self, rate_data: dict) -> Optional[Opportunity]:
        """
        Calculate net yield opportunity from funding rate data.
        
        rate_data: {"exchange": str, "symbol": str, "rate": float, ...}
        """
        exchange = rate_data["exchange"]
        symbol = rate_data["symbol"]
        funding_rate = rate_data["rate"]
        
        # Only consider negative funding (shorts pay longs)
        if funding_rate >= 0:
            return None
        
        # Check whitelist
        if not self.is_whitelisted(symbol):
            return None
        
        # Check minimum funding threshold
        if funding_rate > self.trading.min_funding_rate:
            return None
        
        base_asset = self.extract_base_asset(symbol)
        maker_fee, taker_fee = self.get_fees(exchange)
        
        # Cost calculation for delta-neutral position:
        # Entry: long perp (taker) + short spot (taker) = 2x taker
        # Exit: close both = 2x maker (if we're patient)
        entry_cost = 2 * taker_fee
        exit_cost = 2 * maker_fee
        slippage_cost = self.costs.slippage_estimate * 2  # Both legs
        
        # Borrow cost for spot short (per 8h)
        borrow_cost_8h = self.costs.default_borrow_apr / (3 * 365)  # 3 periods per day
        
        # Net yield per 8h period
        # Funding received (as long) = -funding_rate (since funding is negative)
        funding_received = -funding_rate
        
        # For a single 8h period, we only get funding once
        # Costs are amortized over expected hold time
        # Assume minimum 3 periods (24h) hold
        periods = 3
        amortized_entry_exit = (entry_cost + exit_cost + slippage_cost) / periods
        
        net_yield_8h = funding_received - borrow_cost_8h - amortized_entry_exit
        net_yield_annualized = net_yield_8h * 3 * 365 * 100  # As percentage
        
        # Simple liquidity score (placeholder - would use order book depth)
        # Major assets get higher scores
        major_assets = {"BTC", "ETH", "SOL", "XRP", "DOGE"}
        liquidity_score = 0.9 if base_asset in major_assets else 0.5
        
        return Opportunity(
            exchange=exchange,
            symbol=symbol,
            base_asset=base_asset,
            funding_rate=funding_rate,
            funding_annualized=funding_rate * 3 * 365 * 100,
            entry_cost=entry_cost,
            exit_cost=exit_cost,
            slippage_cost=slippage_cost,
            borrow_cost_8h=borrow_cost_8h,
            net_yield_8h=net_yield_8h,
            net_yield_annualized=net_yield_annualized,
            liquidity_score=liquidity_score,
            timestamp=datetime.utcnow().isoformat()
        )
    
    def score_all(self, rates: list[dict]) -> list[Opportunity]:
        """Score all funding rates and return sorted opportunities"""
        opportunities = []
        for rate in rates:
            opp = self.calculate_opportunity(rate)
            if opp and opp.net_yield_annualized >= self.trading.min_net_yield_pct:
                opportunities.append(opp)
        
        # Sort by net yield (descending)
        opportunities.sort(key=lambda x: x.net_yield_annualized, reverse=True)
        return opportunities


def main():
    # Load funding rates
    with open("../funding_rates.json") as f:
        rates = json.load(f)
    
    config = load_config()
    scorer = OpportunityScorer(config)
    opportunities = scorer.score_all(rates)
    
    print(f"\n{'='*80}")
    print(f"FUNDING ARB OPPORTUNITIES - {datetime.utcnow().isoformat()}Z")
    print(f"Minimum net yield: {config.trading.min_net_yield_pct}% APR")
    print(f"{'='*80}")
    
    if not opportunities:
        print("\nNo opportunities meeting criteria found.")
        return
    
    print(f"\nFound {len(opportunities)} opportunities:\n")
    print(f"{'Exchange':<12} {'Symbol':<15} {'Funding':<12} {'Net Yield':<12} {'Liq':<6}")
    print("-" * 60)
    
    for opp in opportunities[:20]:
        print(f"{opp.exchange:<12} {opp.symbol:<15} {opp.funding_annualized:>10.1f}% {opp.net_yield_annualized:>10.1f}% {opp.liquidity_score:>5.2f}")
    
    # Save opportunities
    with open("../opportunities.json", "w") as f:
        json.dump([o.to_dict() for o in opportunities], f, indent=2)
    
    print(f"\n✓ Saved {len(opportunities)} opportunities to opportunities.json")
    
    # Summary stats
    if opportunities:
        avg_yield = sum(o.net_yield_annualized for o in opportunities) / len(opportunities)
        best = opportunities[0]
        print(f"\n📊 Summary:")
        print(f"   Best opportunity: {best.exchange} {best.symbol} @ {best.net_yield_annualized:.1f}% net APR")
        print(f"   Average net yield: {avg_yield:.1f}%")
        print(f"   Whitelisted assets with opportunities: {len(set(o.base_asset for o in opportunities))}")


if __name__ == "__main__":
    main()
