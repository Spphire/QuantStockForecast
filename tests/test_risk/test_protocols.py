from __future__ import annotations

from risk_management.white_box.protocols import (
    DEFAULT_PEER_COMPARISON_BACKTEST_PROTOCOL,
    get_default_peer_comparison_backtest_protocol,
    strict_white_box_kwargs,
)


def test_default_peer_comparison_protocol_matches_strict_setting() -> None:
    protocol = get_default_peer_comparison_backtest_protocol()

    assert protocol is DEFAULT_PEER_COMPARISON_BACKTEST_PROTOCOL
    assert protocol.mode == "P0 Strict"
    assert protocol.market_scope.market == "US"
    assert protocol.market_scope.frequency == "daily"
    assert protocol.market_scope.benchmark_symbol == "SPY"
    assert protocol.market_scope.prediction_start == "2025-01-01"
    assert protocol.execution.horizon_sessions == 5
    assert protocol.execution.transaction_cost_bps_per_side == 10.0
    assert protocol.walk_forward.train_window_months == 36
    assert protocol.walk_forward.validation_window_months == 6
    assert protocol.walk_forward.test_window_months == 6
    assert protocol.walk_forward.roll_frequency == "monthly"
    assert protocol.walk_forward.purge_window_sessions == 6
    assert protocol.walk_forward.embargo_window_sessions == 1
    assert protocol.portfolio.top_k == 10
    assert protocol.portfolio.max_positions_per_sector == 2
    assert protocol.portfolio.sector_neutralization is True
    assert protocol.liquidity.min_close == 10.0
    assert protocol.liquidity.min_median_dollar_volume_20 == 50_000_000.0
    assert protocol.liquidity.max_vol_20 == 0.04
    assert len(protocol.features.baseline_daily_features) == 12


def test_strict_white_box_kwargs_match_protocol_defaults() -> None:
    kwargs = strict_white_box_kwargs()

    assert kwargs["top_k"] == 10
    assert kwargs["rebalance_step"] == 5
    assert kwargs["benchmark_symbol"] == "SPY"
    assert kwargs["group_column"] == "industry_sector"
    assert kwargs["max_per_group"] == 2
    assert kwargs["sector_neutralization"] is True
    assert kwargs["sector_column"] == "industry_sector"
    assert kwargs["min_close"] == 10.0
    assert kwargs["min_median_dollar_volume_20"] == 50_000_000.0
    assert kwargs["max_vol_20"] == 0.04
    assert kwargs["transaction_cost_bps"] == 10.0
