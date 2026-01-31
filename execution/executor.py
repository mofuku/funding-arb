"""
Execution engine for funding rate arbitrage.
Handles simultaneous long perp + short spot/perp positions.
"""
import asyncio
import hmac
import hashlib
import time
import json
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional
from enum import Enum
import aiohttp

class Side(Enum):
    LONG = "long"
    SHORT = "short"

class OrderType(Enum):
    MARKET = "market"
    LIMIT = "limit"

@dataclass
class Order:
    exchange: str
    symbol: str
    side: Side
    size: float
    order_type: OrderType = OrderType.MARKET
    price: Optional[float] = None
    order_id: Optional[str] = None
    status: str = "pending"
    fill_price: Optional[float] = None
    filled_size: float = 0
    
@dataclass
class Position:
    exchange: str
    symbol: str
    side: Side
    size: float
    entry_price: float
    entry_time: float
    pnl: float = 0
    funding_collected: float = 0

@dataclass
class ArbPosition:
    """Combined delta-neutral position"""
    id: str
    long_leg: Position
    short_leg: Position
    base_asset: str
    entry_time: float
    target_funding_rate: float
    total_funding_collected: float = 0
    total_pnl: float = 0
    status: str = "open"

class ExchangeClient(ABC):
    """Abstract exchange client"""
    
    @abstractmethod
    async def place_order(self, order: Order) -> Order:
        pass
    
    @abstractmethod
    async def cancel_order(self, order_id: str, symbol: str) -> bool:
        pass
    
    @abstractmethod
    async def get_position(self, symbol: str) -> Optional[Position]:
        pass
    
    @abstractmethod
    async def get_balance(self) -> dict:
        pass

class SimulatedClient(ExchangeClient):
    """Simulated exchange for testing"""
    
    def __init__(self, exchange: str, initial_balance: float = 10000):
        self.exchange = exchange
        self.balance = initial_balance
        self.positions: dict[str, Position] = {}
        self.orders: list[Order] = []
        
    async def place_order(self, order: Order) -> Order:
        # Simulate fill
        order.status = "filled"
        order.fill_price = order.price or 100  # Placeholder
        order.filled_size = order.size
        order.order_id = f"sim_{int(time.time()*1000)}"
        
        # Update position
        if order.symbol in self.positions:
            pos = self.positions[order.symbol]
            if pos.side == order.side:
                # Add to position
                new_size = pos.size + order.filled_size
                pos.entry_price = (pos.entry_price * pos.size + order.fill_price * order.filled_size) / new_size
                pos.size = new_size
            else:
                # Reduce/close position
                if order.filled_size >= pos.size:
                    del self.positions[order.symbol]
                else:
                    pos.size -= order.filled_size
        else:
            # New position
            self.positions[order.symbol] = Position(
                exchange=self.exchange,
                symbol=order.symbol,
                side=order.side,
                size=order.filled_size,
                entry_price=order.fill_price,
                entry_time=time.time()
            )
        
        self.orders.append(order)
        return order
    
    async def cancel_order(self, order_id: str, symbol: str) -> bool:
        return True
    
    async def get_position(self, symbol: str) -> Optional[Position]:
        return self.positions.get(symbol)
    
    async def get_balance(self) -> dict:
        return {"USDT": self.balance}

class ArbExecutor:
    """Orchestrates delta-neutral position entry/exit"""
    
    def __init__(self, clients: dict[str, ExchangeClient]):
        self.clients = clients
        self.active_positions: dict[str, ArbPosition] = {}
        
    async def open_position(
        self,
        long_exchange: str,
        short_exchange: str,
        symbol: str,
        base_asset: str,
        size_usd: float,
        funding_rate: float,
    ) -> ArbPosition:
        """
        Open delta-neutral position:
        - Long perp on long_exchange
        - Short perp on short_exchange (or short spot)
        """
        long_client = self.clients[long_exchange]
        short_client = self.clients[short_exchange]
        
        # Calculate size (assuming $100 per unit for simplicity)
        size = size_usd / 100
        
        # Place orders simultaneously
        long_order = Order(
            exchange=long_exchange,
            symbol=symbol,
            side=Side.LONG,
            size=size,
            order_type=OrderType.MARKET,
        )
        short_order = Order(
            exchange=short_exchange,
            symbol=symbol,
            side=Side.SHORT,
            size=size,
            order_type=OrderType.MARKET,
        )
        
        # Execute simultaneously
        long_result, short_result = await asyncio.gather(
            long_client.place_order(long_order),
            short_client.place_order(short_order),
        )
        
        # Create arb position
        pos_id = f"arb_{int(time.time())}"
        arb_pos = ArbPosition(
            id=pos_id,
            long_leg=Position(
                exchange=long_exchange,
                symbol=symbol,
                side=Side.LONG,
                size=long_result.filled_size,
                entry_price=long_result.fill_price,
                entry_time=time.time(),
            ),
            short_leg=Position(
                exchange=short_exchange,
                symbol=symbol,
                side=Side.SHORT,
                size=short_result.filled_size,
                entry_price=short_result.fill_price,
                entry_time=time.time(),
            ),
            base_asset=base_asset,
            entry_time=time.time(),
            target_funding_rate=funding_rate,
        )
        
        self.active_positions[pos_id] = arb_pos
        return arb_pos
    
    async def close_position(self, pos_id: str) -> dict:
        """Close a delta-neutral position"""
        if pos_id not in self.active_positions:
            raise ValueError(f"Position {pos_id} not found")
        
        pos = self.active_positions[pos_id]
        
        # Close both legs
        long_client = self.clients[pos.long_leg.exchange]
        short_client = self.clients[pos.short_leg.exchange]
        
        close_long = Order(
            exchange=pos.long_leg.exchange,
            symbol=pos.long_leg.symbol,
            side=Side.SHORT,  # Close long = sell
            size=pos.long_leg.size,
            order_type=OrderType.MARKET,
        )
        close_short = Order(
            exchange=pos.short_leg.exchange,
            symbol=pos.short_leg.symbol,
            side=Side.LONG,  # Close short = buy
            size=pos.short_leg.size,
            order_type=OrderType.MARKET,
        )
        
        long_result, short_result = await asyncio.gather(
            long_client.place_order(close_long),
            short_client.place_order(close_short),
        )
        
        pos.status = "closed"
        del self.active_positions[pos_id]
        
        return {
            "pos_id": pos_id,
            "total_funding": pos.total_funding_collected,
            "total_pnl": pos.total_pnl,
        }


async def test_executor():
    """Test the execution system"""
    # Create simulated clients
    clients = {
        "binance": SimulatedClient("binance"),
        "bybit": SimulatedClient("bybit"),
    }
    
    executor = ArbExecutor(clients)
    
    # Test opening position
    print("Opening delta-neutral position...")
    pos = await executor.open_position(
        long_exchange="binance",
        short_exchange="bybit",
        symbol="SOLUSDT",
        base_asset="SOL",
        size_usd=1000,
        funding_rate=-0.002,
    )
    
    print(f"✓ Opened position {pos.id}")
    print(f"  Long: {pos.long_leg.size} @ {pos.long_leg.entry_price} on {pos.long_leg.exchange}")
    print(f"  Short: {pos.short_leg.size} @ {pos.short_leg.entry_price} on {pos.short_leg.exchange}")
    
    # Test closing
    print("\nClosing position...")
    result = await executor.close_position(pos.id)
    print(f"✓ Closed position: {result}")

if __name__ == "__main__":
    asyncio.run(test_executor())
