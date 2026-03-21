"""Asset-level checks before sending Alpaca orders."""

from __future__ import annotations

from execution.alpaca.client import AlpacaBroker
from execution.common.execution_models import OrderIntent


def validate_asset_for_order(broker: AlpacaBroker, order: OrderIntent) -> dict:
    asset = broker.get_asset(order.symbol)
    if not bool(asset.get("tradable", False)):
        raise ValueError(f"Asset is not tradable on Alpaca: {order.symbol}")
    if order.allow_fractional and not bool(asset.get("fractionable", False)):
        raise ValueError(f"Asset is not fractionable on Alpaca: {order.symbol}")
    return asset
