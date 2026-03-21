from __future__ import annotations

from dataclasses import asdict, dataclass, field, is_dataclass
from datetime import date
from typing import Protocol, Sequence

from execution.common.execution_models import PositionSnapshot

from execution.managed.brokers.alpaca import BrokerAccount, BrokerClock, BrokerPosition


class BrokerAccountReader(Protocol):
    def get_account(self) -> BrokerAccount:
        ...

    def get_clock(self) -> BrokerClock:
        ...

    def list_positions(self) -> Sequence[BrokerPosition]:
        ...


@dataclass(slots=True, frozen=True)
class PaperAccountSnapshot:
    session_date: date
    cash: float
    equity: float
    gross_exposure: float
    positions: tuple[PositionSnapshot, ...] = ()
    raw: dict[str, object] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        return {
            "session_date": self.session_date.isoformat(),
            "cash": self.cash,
            "equity": self.equity,
            "gross_exposure": self.gross_exposure,
            "positions": [position.to_dict() for position in self.positions],
            "raw": dict(self.raw),
        }


@dataclass(slots=True, frozen=True)
class AccountSyncResult:
    snapshot: PaperAccountSnapshot
    broker_account: BrokerAccount
    broker_positions: tuple[BrokerPosition, ...]
    clock: BrokerClock

    def to_dict(self) -> dict[str, object]:
        return {
            "snapshot": self.snapshot.to_dict(),
            "broker_account": _normalize_mapping(self.broker_account),
            "broker_positions": [_normalize_mapping(position) for position in self.broker_positions],
            "clock": _normalize_mapping(self.clock),
        }


@dataclass(slots=True)
class AlpacaAccountSync:
    broker: BrokerAccountReader

    def sync(self, session_date: date | None = None) -> AccountSyncResult:
        broker_account = self.broker.get_account()
        clock = self.broker.get_clock()
        positions = tuple(self.broker.list_positions())
        effective_date = session_date or clock.timestamp.date()
        equity = float(broker_account.equity)
        cash = float(broker_account.cash)
        position_snapshots = tuple(
            PositionSnapshot(
                symbol=position.symbol,
                qty=float(position.quantity),
                market_value=float(position.market_value),
                current_price=float(position.current_price or position.avg_entry_price or 0.0),
                weight=(float(position.market_value) / equity) if equity else 0.0,
                raw=dict(position.raw),
            )
            for position in positions
        )
        gross_exposure = sum(abs(snapshot.market_value) for snapshot in position_snapshots)
        snapshot = PaperAccountSnapshot(
            session_date=effective_date,
            cash=cash,
            equity=equity,
            gross_exposure=gross_exposure,
            positions=position_snapshots,
            raw={"clock": _normalize_mapping(clock), "broker_account": _normalize_mapping(broker_account)},
        )
        return AccountSyncResult(
            snapshot=snapshot,
            broker_account=broker_account,
            broker_positions=positions,
            clock=clock,
        )


def sync_account_snapshot(
    broker: BrokerAccountReader,
    *,
    session_date: date | None = None,
) -> PaperAccountSnapshot:
    return AlpacaAccountSync(broker).sync(session_date=session_date).snapshot


def _normalize_mapping(value: object) -> dict[str, object]:
    if isinstance(value, dict):
        return dict(value)
    if is_dataclass(value):
        return asdict(value)
    if hasattr(value, "__dict__"):
        return {key: val for key, val in vars(value).items() if not key.startswith("_")}
    return {"repr": repr(value)}

