"""Typed execution-layer models shared by broker adapters and scripts."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(slots=True)
class AccountSnapshot:
    broker: str
    account_id: str
    equity: float
    cash: float
    buying_power: float
    currency: str = "USD"
    raw: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class PositionSnapshot:
    symbol: str
    qty: float
    market_value: float
    current_price: float
    weight: float = 0.0
    raw: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class TargetPosition:
    symbol: str
    target_weight: float
    previous_weight: float
    action: str
    reference_price: float
    score: float
    confidence: float
    rebalance_date: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class OrderIntent:
    symbol: str
    side: str
    delta_notional: float
    reference_price: float
    estimated_qty: float
    submit_notional: float
    submit_qty: float
    target_weight: float
    current_weight: float
    current_notional: float
    target_notional: float
    order_type: str = "market"
    time_in_force: str = "day"
    allow_fractional: bool = True
    submit_as: str = "notional"
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class SubmittedOrder:
    order_id: str
    client_order_id: str
    symbol: str
    side: str
    status: str
    attempt: int = 1
    submit_as: str = "notional"
    requested_notional: float = 0.0
    requested_qty: float = 0.0
    note: str = ""
    raw: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class ExecutionPlan:
    strategy_id: str
    broker: str
    rebalance_date: str
    generated_at: str
    account_equity: float
    planning_equity: float
    account_buying_power: float
    current_positions: list[PositionSnapshot]
    target_positions: list[TargetPosition]
    order_intents: list[OrderIntent]
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "strategy_id": self.strategy_id,
            "broker": self.broker,
            "rebalance_date": self.rebalance_date,
            "generated_at": self.generated_at,
            "account_equity": self.account_equity,
            "planning_equity": self.planning_equity,
            "account_buying_power": self.account_buying_power,
            "current_positions": [item.to_dict() for item in self.current_positions],
            "target_positions": [item.to_dict() for item in self.target_positions],
            "order_intents": [item.to_dict() for item in self.order_intents],
            "notes": list(self.notes),
        }
