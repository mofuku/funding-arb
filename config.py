"""
Configuration for funding rate arbitrage bot.
Copy to config_local.py and fill in credentials.
"""
import os
from dataclasses import dataclass, field
from typing import Optional

@dataclass
class ExchangeConfig:
    api_key: str = ""
    api_secret: str = ""
    passphrase: str = ""  # OKX requires this
    testnet: bool = True  # Start with testnet!

@dataclass  
class TradingConfig:
    # Minimum annualized yield after costs to consider
    min_net_yield_pct: float = 50.0  # 50% APR minimum
    
    # Minimum funding rate per 8h period
    min_funding_rate: float = -0.0015  # -0.15%
    
    # Maximum position size per trade (USD)
    max_position_usd: float = 1000.0
    
    # Total portfolio allocation (USD)
    total_capital_usd: float = 10000.0
    
    # Maximum concurrent positions
    max_positions: int = 5
    
    # Liquidation buffer (margin ratio to maintain)
    liq_buffer_pct: float = 50.0  # Keep 50% buffer above liq price
    
    # Exit triggers
    exit_funding_threshold: float = -0.0001  # Exit when funding > -0.01%
    max_hold_hours: int = 72  # Max 3 days per position
    stop_loss_pct: float = 2.0  # 2% stop loss on the spread

@dataclass
class CostModel:
    """Fee structure per exchange"""
    # Maker/taker fees (as decimal, e.g., 0.0002 = 0.02%)
    binance_maker: float = 0.0002
    binance_taker: float = 0.0004
    bybit_maker: float = 0.0002
    bybit_taker: float = 0.00055
    hyperliquid_maker: float = 0.0002
    hyperliquid_taker: float = 0.0005
    okx_maker: float = 0.0002
    okx_taker: float = 0.0005
    
    # Estimated slippage for $1k position
    slippage_estimate: float = 0.0005  # 0.05%
    
    # Default borrow rate for spot shorts (APR)
    default_borrow_apr: float = 0.30  # 30%

@dataclass
class Config:
    exchanges: dict = field(default_factory=lambda: {
        "binance": ExchangeConfig(),
        "bybit": ExchangeConfig(),
        "hyperliquid": ExchangeConfig(),
        "okx": ExchangeConfig(),
    })
    trading: TradingConfig = field(default_factory=TradingConfig)
    costs: CostModel = field(default_factory=CostModel)
    
    # Whitelist of liquid symbols to consider
    symbol_whitelist: list = field(default_factory=lambda: [
        "BTC", "ETH", "SOL", "DOGE", "XRP", "ADA", "AVAX", "LINK", 
        "DOT", "MATIC", "UNI", "ATOM", "LTC", "BCH", "APT", "ARB",
        "OP", "INJ", "SUI", "SEI", "TIA", "JUP", "PYTH", "JTO",
        "WIF", "BONK", "PEPE", "SHIB", "FIL", "NEAR", "RENDER"
    ])

# Load from environment or config file
def load_config() -> Config:
    config = Config()
    
    # Override from environment
    if os.getenv("BINANCE_API_KEY"):
        config.exchanges["binance"].api_key = os.getenv("BINANCE_API_KEY", "")
        config.exchanges["binance"].api_secret = os.getenv("BINANCE_API_SECRET", "")
    
    if os.getenv("BYBIT_API_KEY"):
        config.exchanges["bybit"].api_key = os.getenv("BYBIT_API_KEY", "")
        config.exchanges["bybit"].api_secret = os.getenv("BYBIT_API_SECRET", "")
    
    if os.getenv("HL_API_KEY"):
        config.exchanges["hyperliquid"].api_key = os.getenv("HL_API_KEY", "")
        config.exchanges["hyperliquid"].api_secret = os.getenv("HL_API_SECRET", "")
    
    return config

if __name__ == "__main__":
    cfg = load_config()
    print(f"Trading config: min_net_yield={cfg.trading.min_net_yield_pct}%")
    print(f"Whitelisted symbols: {len(cfg.symbol_whitelist)}")
