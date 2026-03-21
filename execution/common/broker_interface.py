"""Abstract broker interface used by execution scripts."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from execution.common.execution_models import (
    AccountSnapshot,
    OrderIntent,
    PositionSnapshot,
    SubmittedOrder,
)


class BrokerInterface(ABC):
    @abstractmethod
    def get_account_snapshot(self) -> AccountSnapshot:
        raise NotImplementedError

    @abstractmethod
    def list_positions(self) -> list[PositionSnapshot]:
        raise NotImplementedError

    @abstractmethod
    def submit_order(self, order: OrderIntent, *, client_order_id: str) -> SubmittedOrder:
        raise NotImplementedError

    @abstractmethod
    def cancel_open_orders(self) -> list[str]:
        raise NotImplementedError

    @abstractmethod
    def get_order(self, order_id: str) -> dict[str, Any]:
        raise NotImplementedError
