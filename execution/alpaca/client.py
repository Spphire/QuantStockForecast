"""Minimal Alpaca REST adapter for paper/live trading."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests

from execution.common.broker_interface import BrokerInterface
from execution.common.execution_models import (
    AccountSnapshot,
    OrderIntent,
    PositionSnapshot,
    SubmittedOrder,
)


DEFAULT_PAPER_BASE_URL = "https://paper-api.alpaca.markets"
PROJECT_ROOT = Path(__file__).resolve().parents[2]
LOCAL_CONFIG_PATH = PROJECT_ROOT / "configs" / "alpaca_accounts.local.json"


@dataclass(slots=True)
class AlpacaCredentials:
    api_key: str
    secret_key: str
    base_url: str


def load_alpaca_credentials(env_prefix: str) -> AlpacaCredentials:
    api_key = os.getenv(f"{env_prefix}_API_KEY", "").strip()
    secret_key = os.getenv(f"{env_prefix}_SECRET_KEY", "").strip()
    base_url = os.getenv(f"{env_prefix}_BASE_URL", DEFAULT_PAPER_BASE_URL).strip()

    if (not api_key or not secret_key) and LOCAL_CONFIG_PATH.exists():
        payload = json.loads(LOCAL_CONFIG_PATH.read_text(encoding="utf-8"))
        account_config = payload.get(env_prefix, {})
        api_key = api_key or str(account_config.get("api_key", "")).strip()
        secret_key = secret_key or str(account_config.get("secret_key", "")).strip()
        base_url = base_url or str(account_config.get("base_url", DEFAULT_PAPER_BASE_URL)).strip()

    if not api_key or not secret_key:
        raise EnvironmentError(
            f"Missing Alpaca credentials for prefix {env_prefix}. "
            f"Expected environment variables or {LOCAL_CONFIG_PATH}."
        )
    normalized_base_url = base_url.rstrip("/")
    if normalized_base_url.endswith("/v2"):
        normalized_base_url = normalized_base_url[: -len("/v2")]
    return AlpacaCredentials(
        api_key=api_key,
        secret_key=secret_key,
        base_url=normalized_base_url,
    )


class AlpacaBroker(BrokerInterface):
    def __init__(self, credentials: AlpacaCredentials) -> None:
        self.credentials = credentials
        self.session = requests.Session()
        self.session.headers.update(
            {
                "APCA-API-KEY-ID": credentials.api_key,
                "APCA-API-SECRET-KEY": credentials.secret_key,
                "Content-Type": "application/json",
            }
        )

    def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        response = self.session.request(
            method,
            f"{self.credentials.base_url}{path}",
            timeout=30,
            **kwargs,
        )
        response.raise_for_status()
        if not response.content:
            return {}
        return response.json()

    def get_account_snapshot(self) -> AccountSnapshot:
        payload = self._request("GET", "/v2/account")
        return AccountSnapshot(
            broker="alpaca",
            account_id=str(payload.get("id", "")),
            equity=float(payload.get("equity", 0.0)),
            cash=float(payload.get("cash", 0.0)),
            buying_power=float(payload.get("buying_power", 0.0)),
            currency=str(payload.get("currency", "USD")),
            raw=payload,
        )

    def list_positions(self) -> list[PositionSnapshot]:
        payload = self._request("GET", "/v2/positions")
        positions: list[PositionSnapshot] = []
        for row in payload:
            positions.append(
                PositionSnapshot(
                    symbol=str(row.get("symbol", "")),
                    qty=float(row.get("qty", 0.0)),
                    market_value=float(row.get("market_value", 0.0)),
                    current_price=float(row.get("current_price", 0.0)),
                    raw=row,
                )
            )
        return positions

    def get_asset(self, symbol: str) -> dict[str, Any]:
        return self._request("GET", f"/v2/assets/{symbol}")

    def list_open_orders(self) -> list[dict[str, Any]]:
        payload = self._request("GET", "/v2/orders", params={"status": "open"})
        return list(payload)

    def cancel_open_orders(self) -> list[str]:
        open_orders = self.list_open_orders()
        canceled: list[str] = []
        for order in open_orders:
            order_id = str(order.get("id", ""))
            if not order_id:
                continue
            self._request("DELETE", f"/v2/orders/{order_id}")
            canceled.append(order_id)
        return canceled

    def get_order(self, order_id: str) -> dict[str, Any]:
        return self._request("GET", f"/v2/orders/{order_id}")

    def submit_order(self, order: OrderIntent, *, client_order_id: str) -> SubmittedOrder:
        payload: dict[str, Any] = {
            "symbol": order.symbol,
            "side": order.side,
            "type": order.order_type,
            "time_in_force": order.time_in_force,
            "client_order_id": client_order_id,
        }

        if order.submit_as == "notional":
            notional = order.submit_notional if order.submit_notional > 0 else abs(order.delta_notional)
            payload["notional"] = round(notional, 2)
        else:
            if order.reference_price <= 0:
                raise ValueError(f"Cannot derive qty for {order.symbol} because reference_price <= 0.")
            qty = order.submit_qty if order.submit_qty > 0 else order.estimated_qty
            if qty <= 0:
                qty = abs(order.delta_notional) / order.reference_price
            if order.allow_fractional:
                payload["qty"] = round(qty, 6)
            else:
                payload["qty"] = int(qty)

        response = self._request("POST", "/v2/orders", json=payload)
        return SubmittedOrder(
            order_id=str(response.get("id", "")),
            client_order_id=str(response.get("client_order_id", client_order_id)),
            symbol=order.symbol,
            side=order.side,
            status=str(response.get("status", "")),
            submit_as=order.submit_as,
            requested_notional=float(payload.get("notional", 0.0) or 0.0),
            requested_qty=float(payload.get("qty", 0.0) or 0.0),
            raw=response,
        )
