from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Mapping, Sequence

from execution.alpaca.client import AlpacaBroker as LegacyAlpacaBroker
from execution.alpaca.client import AlpacaCredentials


def _to_float(value: Any) -> float:
    if value in (None, ""):
        return 0.0
    return float(value)


def _to_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.lower() in {"true", "1", "yes"}
    return bool(value)


def _to_datetime(value: Any) -> datetime | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))


@dataclass(slots=True, frozen=True)
class BrokerClock:
    timestamp: datetime
    is_open: bool
    next_open: datetime | None = None
    next_close: datetime | None = None
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True, frozen=True)
class BrokerAccount:
    account_id: str
    status: str
    cash: float
    equity: float
    buying_power: float
    portfolio_value: float
    long_market_value: float
    short_market_value: float
    pattern_day_trader: bool
    trading_blocked: bool
    account_blocked: bool
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True, frozen=True)
class BrokerPosition:
    symbol: str
    quantity: float
    market_value: float
    avg_entry_price: float
    cost_basis: float
    unrealized_pl: float
    side: str | None = None
    current_price: float | None = None
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True, frozen=True)
class BrokerOrder:
    order_id: str
    client_order_id: str | None
    symbol: str
    side: str
    order_type: str
    time_in_force: str
    status: str
    quantity: float | None
    filled_quantity: float | None
    filled_avg_price: float | None
    limit_price: float | None
    submitted_at: datetime | None
    updated_at: datetime | None
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class AlpacaTradingAdapter:
    """Thin adapter over the repository's legacy Alpaca broker."""

    broker: LegacyAlpacaBroker

    @classmethod
    def from_env(cls) -> "AlpacaTradingAdapter":
        return cls(broker=LegacyAlpacaBroker.from_env())

    @classmethod
    def from_credentials(cls, credentials: AlpacaCredentials) -> "AlpacaTradingAdapter":
        return cls(broker=LegacyAlpacaBroker(credentials))

    @classmethod
    def from_legacy_broker(cls, broker: LegacyAlpacaBroker) -> "AlpacaTradingAdapter":
        return cls(broker=broker)

    def is_paper_trading_environment(self) -> bool:
        base_url = str(getattr(self.broker.credentials, "base_url", "")).lower()
        return "paper" in base_url

    def get_account(self) -> BrokerAccount:
        snapshot = self.broker.get_account_snapshot()
        raw = getattr(snapshot, "raw", {})
        return BrokerAccount(
            account_id=str(getattr(snapshot, "account_id", "")),
            status=str(raw.get("status", "active")) if isinstance(raw, Mapping) else "active",
            cash=_to_float(getattr(snapshot, "cash", 0.0)),
            equity=_to_float(getattr(snapshot, "equity", 0.0)),
            buying_power=_to_float(getattr(snapshot, "buying_power", 0.0)),
            portfolio_value=_to_float(raw.get("portfolio_value", getattr(snapshot, "equity", 0.0))) if isinstance(raw, Mapping) else _to_float(getattr(snapshot, "equity", 0.0)),
            long_market_value=_to_float(raw.get("long_market_value", 0.0)) if isinstance(raw, Mapping) else 0.0,
            short_market_value=_to_float(raw.get("short_market_value", 0.0)) if isinstance(raw, Mapping) else 0.0,
            pattern_day_trader=_to_bool(raw.get("pattern_day_trader", False)) if isinstance(raw, Mapping) else False,
            trading_blocked=_to_bool(raw.get("trading_blocked", False)) if isinstance(raw, Mapping) else False,
            account_blocked=_to_bool(raw.get("account_blocked", False)) if isinstance(raw, Mapping) else False,
            raw=dict(raw) if isinstance(raw, Mapping) else {},
        )

    def get_clock(self) -> BrokerClock:
        payload = self.broker.get_clock()
        if not isinstance(payload, Mapping):
            raise RuntimeError("Unexpected Alpaca clock payload shape.")
        return BrokerClock(
            timestamp=_to_datetime(payload.get("timestamp")) or datetime.utcnow(),
            is_open=_to_bool(payload.get("is_open")),
            next_open=_to_datetime(payload.get("next_open")),
            next_close=_to_datetime(payload.get("next_close")),
            raw=dict(payload),
        )

    def list_positions(self) -> list[BrokerPosition]:
        positions: list[BrokerPosition] = []
        for item in self.broker.list_positions():
            raw = getattr(item, "raw", {})
            positions.append(
                BrokerPosition(
                    symbol=str(getattr(item, "symbol", "")),
                    quantity=_to_float(getattr(item, "qty", getattr(item, "quantity", 0.0))),
                    market_value=_to_float(getattr(item, "market_value", 0.0)),
                    avg_entry_price=_to_float(getattr(item, "avg_entry_price", 0.0)),
                    cost_basis=_to_float(getattr(item, "cost_basis", 0.0)),
                    unrealized_pl=_to_float(getattr(item, "unrealized_pl", 0.0)),
                    side=str(getattr(item, "side", "")) if getattr(item, "side", None) is not None else None,
                    current_price=_to_float(getattr(item, "current_price", 0.0))
                    if getattr(item, "current_price", None) is not None
                    else None,
                    raw=dict(raw) if isinstance(raw, Mapping) else {},
                )
            )
        return positions

    def list_open_orders(self) -> list[BrokerOrder]:
        return self.list_orders(status="open")

    def list_orders(
        self,
        *,
        status: str | None = None,
        symbols: Sequence[str] | None = None,
        limit: int | None = None,
        nested: bool | None = None,
        after: str | None = None,
        until: str | None = None,
        direction: str | None = None,
    ) -> list[BrokerOrder]:
        getter = getattr(self.broker, "list_orders", None)
        if callable(getter):
            payload = getter(
                status=status,
                symbols=list(symbols) if symbols else None,
                limit=limit,
                nested=nested,
                after=after,
                until=until,
                direction=direction,
            )
        else:
            payload = self.broker.list_open_orders() if status in (None, "open") else []

        wanted_symbols = {symbol for symbol in symbols} if symbols else None
        orders: list[BrokerOrder] = []
        for item in payload:
            raw = getattr(item, "raw", {})
            order = BrokerOrder(
                order_id=str(getattr(item, "order_id", getattr(item, "id", ""))),
                client_order_id=str(getattr(item, "client_order_id", "")) if getattr(item, "client_order_id", None) is not None else None,
                symbol=str(getattr(item, "symbol", "")),
                side=str(getattr(item, "side", "")),
                order_type=str(getattr(item, "order_type", getattr(item, "type", ""))),
                time_in_force=str(getattr(item, "time_in_force", "")),
                status=str(getattr(item, "status", "")),
                quantity=_to_float(getattr(item, "quantity", getattr(item, "qty", 0.0)))
                if getattr(item, "quantity", getattr(item, "qty", None)) is not None
                else None,
                filled_quantity=_to_float(getattr(item, "filled_quantity", getattr(item, "filled_qty", 0.0)))
                if getattr(item, "filled_quantity", getattr(item, "filled_qty", None)) is not None
                else None,
                filled_avg_price=_to_float(getattr(item, "filled_avg_price", 0.0))
                if getattr(item, "filled_avg_price", None) is not None
                else None,
                limit_price=_to_float(getattr(item, "limit_price", 0.0))
                if getattr(item, "limit_price", None) is not None
                else None,
                submitted_at=_to_datetime(getattr(item, "submitted_at", getattr(item, "created_at", None))),
                updated_at=_to_datetime(getattr(item, "updated_at", None)),
                raw=dict(raw) if isinstance(raw, Mapping) else {},
            )
            if wanted_symbols is not None and order.symbol not in wanted_symbols:
                continue
            orders.append(order)
        if limit is not None:
            return orders[: max(limit, 0)]
        return orders

    def get_order(self, order_id: str) -> BrokerOrder:
        item = self.broker.get_order(order_id)
        raw = getattr(item, "raw", {})
        return BrokerOrder(
            order_id=str(getattr(item, "order_id", getattr(item, "id", ""))),
            client_order_id=str(getattr(item, "client_order_id", "")) if getattr(item, "client_order_id", None) is not None else None,
            symbol=str(getattr(item, "symbol", "")),
            side=str(getattr(item, "side", "")),
            order_type=str(getattr(item, "order_type", getattr(item, "type", ""))),
            time_in_force=str(getattr(item, "time_in_force", "")),
            status=str(getattr(item, "status", "")),
            quantity=_to_float(getattr(item, "quantity", getattr(item, "qty", 0.0)))
            if getattr(item, "quantity", getattr(item, "qty", None)) is not None
            else None,
            filled_quantity=_to_float(getattr(item, "filled_quantity", getattr(item, "filled_qty", 0.0)))
            if getattr(item, "filled_quantity", getattr(item, "filled_qty", None)) is not None
            else None,
            filled_avg_price=_to_float(getattr(item, "filled_avg_price", 0.0))
            if getattr(item, "filled_avg_price", None) is not None
            else None,
            limit_price=_to_float(getattr(item, "limit_price", 0.0))
            if getattr(item, "limit_price", None) is not None
            else None,
            submitted_at=_to_datetime(getattr(item, "submitted_at", getattr(item, "created_at", None))),
            updated_at=_to_datetime(getattr(item, "updated_at", None)),
            raw=dict(raw) if isinstance(raw, Mapping) else {},
        )

    def cancel_order(self, order_id: str) -> BrokerOrder:
        result = getattr(self.broker, "cancel_order", None)
        if callable(result):
            result(order_id)
        else:
            self.broker.cancel_open_orders()
        return self.get_order(order_id)

    def cancel_open_orders(self) -> list[str]:
        return list(self.broker.cancel_open_orders())
