"""Baseline generators used to contextualize white-box strategy backtests."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from data_module.common.stock_schema import normalize_dataframe
from data_module.fetchers.scripts.fetch_stock_history import fetch_stooq_history
from model_prediction.common.signal_interface import standardize_symbol
from risk_management.white_box.liquidity_rules import apply_liquidity_filters


def max_drawdown(equity_curve: pd.Series) -> float:
    running_max = equity_curve.cummax()
    drawdown = equity_curve / running_max - 1.0
    return float(drawdown.min())


def annualized_return(total_return: float, periods: int, rebalances_per_year: float) -> float | None:
    if periods <= 0 or total_return <= -1 or rebalances_per_year <= 0:
        return None
    years = periods / rebalances_per_year
    if years <= 0:
        return None
    return float((1 + total_return) ** (1 / years) - 1)


def load_predictions_schedule(
    predictions_csv: str | Path,
    *,
    rebalance_step: int = 0,
) -> dict[str, Any]:
    predictions_path = Path(predictions_csv)
    frame = pd.read_csv(predictions_path, encoding="utf-8-sig")
    frame["date"] = pd.to_datetime(frame["date"], errors="coerce")
    frame = frame.dropna(subset=["date"]).copy()
    return_column = next(
        (column for column in frame.columns if column.startswith("target_return_")),
        "",
    )
    if not return_column:
        raise ValueError(f"Could not infer target_return_* column from {predictions_path}.")
    horizon = int(return_column.split("_")[-1].rstrip("d"))
    step = rebalance_step or horizon
    dates = sorted(frame["date"].dt.strftime("%Y-%m-%d").unique())
    rebalance_dates = dates[:: max(step, 1)]
    if not rebalance_dates:
        raise ValueError(f"No rebalance dates available in {predictions_path}.")
    return {
        "predictions_csv": str(predictions_path),
        "return_column": return_column,
        "horizon": horizon,
        "rebalance_step": step,
        "eval_start": rebalance_dates[0],
        "eval_end": rebalance_dates[-1],
        "rebalance_dates": rebalance_dates,
    }


def load_universe_history(
    universe_csv: str | Path,
    *,
    eval_start: str,
    eval_end: str,
    horizon: int,
    momentum_lookback: int = 20,
) -> pd.DataFrame:
    universe_path = Path(universe_csv)
    df = pd.read_csv(universe_path, encoding="utf-8-sig")
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df["symbol"] = df["symbol"].map(standardize_symbol)
    df = df.dropna(subset=["date"]).sort_values(["symbol", "date"], kind="stable").copy()

    grouped = df.groupby("symbol", group_keys=False)
    df["realized_return"] = grouped["close"].shift(-horizon) / df["close"] - 1.0
    df["momentum_20d"] = grouped["close"].pct_change(momentum_lookback)

    start_ts = pd.to_datetime(eval_start)
    end_ts = pd.to_datetime(eval_end)
    df = df[(df["date"] >= start_ts) & (df["date"] <= end_ts)].copy()
    return df


def spy_cache_path(start: str, end: str) -> Path:
    project_root = Path(__file__).resolve().parents[2]
    return project_root / "data" / "interim" / "stooq" / f"SPY_{start.replace('-', '')}_{end.replace('-', '')}_normalized.csv"


def load_or_fetch_spy_history(
    *,
    eval_start: str,
    eval_end: str,
    horizon: int,
) -> pd.DataFrame:
    cache_path = spy_cache_path(eval_start, eval_end)
    if cache_path.exists():
        spy_df = pd.read_csv(cache_path, encoding="utf-8-sig")
    else:
        raw_df, provider_label = fetch_stooq_history("SPY", eval_start, eval_end)
        spy_df = normalize_dataframe(raw_df, provider=provider_label, adjust="none")
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        spy_df.to_csv(cache_path, index=False, encoding="utf-8")

    spy_df["date"] = pd.to_datetime(spy_df["date"], errors="coerce")
    spy_df["symbol"] = spy_df["symbol"].map(standardize_symbol)
    spy_df = spy_df.dropna(subset=["date"]).sort_values("date", kind="stable").copy()
    spy_df["realized_return"] = spy_df["close"].shift(-horizon) / spy_df["close"] - 1.0
    return spy_df


def summarize_baseline_periods(
    periods_df: pd.DataFrame,
    *,
    baseline_name: str,
    rebalance_step: int,
    transaction_cost_bps: float,
    description: str,
    symbol_count: int,
) -> dict[str, Any]:
    total_return = float(periods_df["equity"].iloc[-1] - 1.0)
    summary = {
        "baseline_name": baseline_name,
        "baseline_type": "baseline",
        "periods": int(len(periods_df)),
        "symbol_count": symbol_count,
        "transaction_cost_bps": transaction_cost_bps,
        "total_return": total_return,
        "mean_period_return": float(periods_df["period_return"].mean()),
        "mean_gross_period_return": float(periods_df["gross_period_return"].mean()),
        "mean_turnover": float(periods_df["turnover"].mean()),
        "total_transaction_cost": float(periods_df["transaction_cost"].sum()),
        "win_rate": float((periods_df["period_return"] > 0).mean()),
        "max_drawdown": max_drawdown(periods_df["equity"]),
        "annualized_return": annualized_return(total_return, len(periods_df), 252 / max(rebalance_step, 1)),
        "description": description,
    }
    return summary


def save_baseline_result(
    output_dir: str | Path,
    periods_df: pd.DataFrame,
    summary: dict[str, Any],
) -> dict[str, Path]:
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    periods_path = output_path / "baseline_periods.csv"
    summary_path = output_path / "baseline_summary.json"
    periods_df.to_csv(periods_path, index=False, encoding="utf-8")
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return {
        "periods_path": periods_path,
        "summary_path": summary_path,
    }


def build_buy_and_hold_baseline(
    history_df: pd.DataFrame,
    *,
    rebalance_dates: list[str],
    rebalance_step: int,
    transaction_cost_bps: float,
    baseline_name: str,
    description: str,
    selected_symbols: list[str],
) -> tuple[pd.DataFrame, dict[str, Any]]:
    selected_set = {standardize_symbol(symbol) for symbol in selected_symbols}
    if not selected_set:
        raise ValueError(f"{baseline_name} does not have any selected symbols.")

    working = history_df[history_df["symbol"].isin(selected_set)].copy()
    if working.empty:
        raise ValueError(f"{baseline_name} has no price history for selected symbols.")

    rebalance_set = set(rebalance_dates)
    working = working[working["date"].dt.strftime("%Y-%m-%d").isin(rebalance_set)].copy()
    if working.empty:
        raise ValueError(f"{baseline_name} has no rows after rebalance-date alignment.")

    holdings = {symbol: 1.0 / len(selected_set) for symbol in sorted(selected_set)}
    periods: list[dict[str, Any]] = []
    equity = 1.0
    cost_rate = transaction_cost_bps / 10000.0

    for index, rebalance_date in enumerate(rebalance_dates):
        date_slice = working[working["date"].dt.strftime("%Y-%m-%d") == rebalance_date].copy()
        current = date_slice[date_slice["symbol"].isin(holdings)].copy()
        if current.empty:
            continue

        weights = {symbol: weight for symbol, weight in holdings.items() if symbol in set(current["symbol"])}
        total_weight = sum(weights.values())
        if total_weight <= 0:
            continue
        weights = {symbol: value / total_weight for symbol, value in weights.items()}
        current["weight"] = current["symbol"].map(weights).fillna(0.0)

        gross_return = float((current["weight"] * current["realized_return"].fillna(0.0)).sum())
        turnover = 1.0 if index == 0 else 0.0
        cost = turnover * cost_rate
        period_return = gross_return - cost
        equity *= 1 + period_return

        next_values = {
            row["symbol"]: weights[row["symbol"]] * (1.0 + float(row["realized_return"]))
            for _, row in current.iterrows()
            if pd.notna(row["realized_return"])
        }
        total_next = sum(next_values.values())
        if total_next > 0:
            holdings = {symbol: value / total_next for symbol, value in next_values.items()}

        periods.append(
            {
                "rebalance_date": rebalance_date,
                "selected_count": int(len(current)),
                "gross_period_return": gross_return,
                "transaction_cost": cost,
                "turnover": turnover,
                "period_return": period_return,
                "equity": equity,
                "description": description,
            }
        )

    if not periods:
        raise ValueError(f"{baseline_name} did not generate any periods.")

    periods_df = pd.DataFrame(periods)
    summary = summarize_baseline_periods(
        periods_df,
        baseline_name=baseline_name,
        rebalance_step=rebalance_step,
        transaction_cost_bps=transaction_cost_bps,
        description=description,
        symbol_count=len(selected_set),
    )
    return periods_df, summary


def build_universe_equal_weight_buy_hold(
    universe_df: pd.DataFrame,
    *,
    rebalance_dates: list[str],
    rebalance_step: int,
    transaction_cost_bps: float,
    min_close: float = 0.0,
    max_close: float = 0.0,
    min_amount: float = 0.0,
    min_turnover: float = 0.0,
    min_volume: float = 0.0,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    if not rebalance_dates:
        raise ValueError("No rebalance_dates provided for equal-weight buy-and-hold baseline.")
    first_date = rebalance_dates[0]
    initial_slice = universe_df[universe_df["date"].dt.strftime("%Y-%m-%d") == first_date].copy()
    initial_slice = apply_liquidity_filters(
        initial_slice,
        min_close=min_close,
        max_close=max_close,
        min_amount=min_amount,
        min_turnover=min_turnover,
        min_volume=min_volume,
    )
    selected_symbols = sorted(initial_slice["symbol"].dropna().astype(str).unique().tolist())
    return build_buy_and_hold_baseline(
        universe_df,
        rebalance_dates=rebalance_dates,
        rebalance_step=rebalance_step,
        transaction_cost_bps=transaction_cost_bps,
        baseline_name="universe_equal_weight_buy_hold",
        description="Equal-weight buy-and-hold of the investable universe at the first rebalance date.",
        selected_symbols=selected_symbols,
    )


def build_spy_buy_hold(
    spy_df: pd.DataFrame,
    *,
    rebalance_dates: list[str],
    rebalance_step: int,
    transaction_cost_bps: float,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    return build_buy_and_hold_baseline(
        spy_df,
        rebalance_dates=rebalance_dates,
        rebalance_step=rebalance_step,
        transaction_cost_bps=transaction_cost_bps,
        baseline_name="spy_buy_hold",
        description="Buy-and-hold of SPY across the same evaluation window and 5-day reporting schedule.",
        selected_symbols=["SPY"],
    )


def build_momentum_predictions(
    universe_df: pd.DataFrame,
    *,
    output_csv: str | Path,
    horizon: int,
) -> Path:
    working = universe_df.copy()
    working = working.dropna(subset=["realized_return", "momentum_20d"]).copy()
    if working.empty:
        raise ValueError("Momentum baseline has no rows after date alignment and feature preparation.")

    predictions = working[
        [column for column in ["date", "symbol", "close", "amount", "turnover", "volume"] if column in working.columns]
    ].copy()
    predictions[f"target_return_{horizon}d"] = working["realized_return"]
    predictions["pred_return"] = working["momentum_20d"]
    output_path = Path(output_csv)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    predictions["date"] = predictions["date"].dt.strftime("%Y-%m-%d")
    predictions.to_csv(output_path, index=False, encoding="utf-8")
    return output_path
