"""Frozen strict peer-comparison backtest protocol for white-box risk runs."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field


@dataclass(slots=True, frozen=True)
class MarketScope:
    market: str = "US"
    frequency: str = "daily"
    benchmark_symbol: str = "SPY"
    prediction_start: str = "2025-01-01"


@dataclass(slots=True, frozen=True)
class WalkForwardSetting:
    train_window_months: int = 36
    validation_window_months: int = 6
    test_window_months: int = 6
    roll_frequency: str = "monthly"
    purge_window_sessions: int = 6
    embargo_window_sessions: int = 1


@dataclass(slots=True, frozen=True)
class PortfolioSetting:
    long_only: bool = True
    top_k: int = 10
    weighting: str = "equal"
    max_position_weight: float = 1.0
    max_gross_exposure: float = 1.0
    max_positions_per_sector: int = 2
    sector_column: str = "industry_sector"
    sector_neutralization: bool = True


@dataclass(slots=True, frozen=True)
class LiquiditySetting:
    min_close: float = 10.0
    min_median_dollar_volume_20: float = 50_000_000.0
    max_vol_20: float = 0.04


@dataclass(slots=True, frozen=True)
class ExecutionSetting:
    horizon_sessions: int = 5
    transaction_cost_bps_per_side: float = 10.0
    order_policy: str = "market_on_open"
    initial_equity: float = 1_000_000.0


@dataclass(slots=True, frozen=True)
class FeatureSetting:
    baseline_daily_features: tuple[str, ...] = (
        "gap_1",
        "ret_1d",
        "mom_5",
        "mom_10",
        "mom_20",
        "mom_60",
        "vol_20",
        "vol_60",
        "range_1d",
        "volume_ratio_20",
        "rel_mom_20",
        "rel_mom_60",
    )


@dataclass(slots=True, frozen=True)
class PeerComparisonBacktestProtocol:
    mode: str = "P0 Strict"
    market_scope: MarketScope = field(default_factory=MarketScope)
    walk_forward: WalkForwardSetting = field(default_factory=WalkForwardSetting)
    portfolio: PortfolioSetting = field(default_factory=PortfolioSetting)
    liquidity: LiquiditySetting = field(default_factory=LiquiditySetting)
    execution: ExecutionSetting = field(default_factory=ExecutionSetting)
    features: FeatureSetting = field(default_factory=FeatureSetting)

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


DEFAULT_PEER_COMPARISON_BACKTEST_PROTOCOL = PeerComparisonBacktestProtocol()


def get_default_peer_comparison_backtest_protocol() -> PeerComparisonBacktestProtocol:
    """Return the frozen strict peer-comparison protocol."""

    return DEFAULT_PEER_COMPARISON_BACKTEST_PROTOCOL


def strict_white_box_kwargs(
    protocol: PeerComparisonBacktestProtocol | None = None,
) -> dict[str, object]:
    """Translate strict protocol values into `run_white_box_risk` kwargs."""

    resolved = protocol or get_default_peer_comparison_backtest_protocol()
    return {
        "top_k": resolved.portfolio.top_k,
        "weighting": resolved.portfolio.weighting,
        "max_position_weight": resolved.portfolio.max_position_weight,
        "max_gross_exposure": resolved.portfolio.max_gross_exposure,
        "group_column": resolved.portfolio.sector_column,
        "max_per_group": resolved.portfolio.max_positions_per_sector,
        "sector_column": resolved.portfolio.sector_column,
        "sector_neutralization": resolved.portfolio.sector_neutralization,
        "min_close": resolved.liquidity.min_close,
        "min_median_dollar_volume_20": resolved.liquidity.min_median_dollar_volume_20,
        "max_vol_20": resolved.liquidity.max_vol_20,
        "transaction_cost_bps": resolved.execution.transaction_cost_bps_per_side,
        "benchmark_symbol": resolved.market_scope.benchmark_symbol,
        "rebalance_step": resolved.execution.horizon_sessions,
    }
