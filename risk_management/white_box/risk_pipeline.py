"""End-to-end white-box risk pipeline for model signals."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from model_prediction.common.signal_interface import load_signal_frame, standardize_symbol
from risk_management.white_box.exposure_rules import capped_selection, ensure_group_columns
from risk_management.white_box.liquidity_rules import apply_liquidity_filters
from risk_management.white_box.position_sizing import (
    apply_min_trade_weight,
    blend_toward_target,
    compute_position_weights,
    normalize_weight_dict,
    portfolio_turnover,
)
from risk_management.white_box.signal_guard import apply_signal_guards


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


def merge_metadata(df: pd.DataFrame, metadata_csv: str) -> pd.DataFrame:
    metadata_path = Path(metadata_csv)
    metadata_df = pd.read_csv(metadata_path, encoding="utf-8-sig")
    metadata_df["symbol"] = metadata_df["symbol"].map(standardize_symbol)
    working = df.copy()
    working["symbol"] = working["symbol"].map(standardize_symbol)
    return working.merge(metadata_df, on="symbol", how="left", suffixes=("", "_meta"))


def classify_weight_action(previous_weight: float, target_weight: float, *, eps: float = 1e-9) -> str:
    if previous_weight <= eps and target_weight > eps:
        return "open"
    if previous_weight > eps and target_weight <= eps:
        return "exit"
    delta = target_weight - previous_weight
    if delta > eps:
        return "add"
    if delta < -eps:
        return "reduce"
    return "hold"


def build_rebalance_actions(
    rebalance_date: str,
    selected: pd.DataFrame,
    previous_weights: dict[str, float],
) -> pd.DataFrame:
    selected_indexed = selected.set_index("symbol", drop=False) if not selected.empty else pd.DataFrame()
    current_weights = (
        selected.set_index("symbol")["weight"].astype(float).to_dict() if not selected.empty else {}
    )
    rows: list[dict[str, object]] = []

    for symbol in sorted(set(previous_weights) | set(current_weights)):
        previous_weight = float(previous_weights.get(symbol, 0.0))
        target_weight = float(current_weights.get(symbol, 0.0))
        action = classify_weight_action(previous_weight, target_weight)
        row = {
            "rebalance_date": rebalance_date,
            "symbol": str(symbol),
            "previous_weight": previous_weight,
            "target_weight": target_weight,
            "weight_change": target_weight - previous_weight,
            "abs_weight_change": abs(target_weight - previous_weight),
            "action": action,
        }
        if not selected.empty and symbol in selected_indexed.index:
            selected_row = selected_indexed.loc[symbol]
            if isinstance(selected_row, pd.DataFrame):
                selected_row = selected_row.iloc[0]
            for column, value in selected_row.items():
                if column not in row:
                    row[column] = value
        rows.append(row)

    return pd.DataFrame(rows)


def select_with_hysteresis(
    eligible: pd.DataFrame,
    previous_weights: dict[str, float],
    *,
    top_k: int,
    group_column: str = "",
    max_per_group: int = 0,
    secondary_group_column: str = "",
    secondary_max_per_group: int = 0,
    hold_buffer: float = 0.0,
) -> pd.DataFrame:
    if eligible.empty:
        return eligible.copy()

    working = eligible.copy()
    held_symbols = {
        str(symbol)
        for symbol, weight in previous_weights.items()
        if float(weight) > 1e-12
    }
    working["was_held"] = working["symbol"].astype(str).isin(held_symbols)
    working["selection_score"] = pd.to_numeric(working["score"], errors="coerce").fillna(0.0)
    if hold_buffer > 0:
        working.loc[working["was_held"], "selection_score"] += hold_buffer

    selected = capped_selection(
        working,
        score_column="selection_score",
        top_k=top_k,
        group_column=group_column,
        max_per_group=max_per_group,
        secondary_group_column=secondary_group_column,
        secondary_max_per_group=secondary_max_per_group,
    )
    return selected.sort_values("selection_score", ascending=False, kind="stable").copy()


def build_weighted_portfolio(
    date_slice: pd.DataFrame,
    current_weights: dict[str, float],
) -> pd.DataFrame:
    if not current_weights:
        return date_slice.iloc[0:0].copy()

    normalized_weights = normalize_weight_dict(current_weights)
    if not normalized_weights:
        return date_slice.iloc[0:0].copy()

    portfolio = date_slice[date_slice["symbol"].astype(str).isin(normalized_weights)].copy()
    if portfolio.empty:
        return portfolio

    portfolio["weight"] = portfolio["symbol"].astype(str).map(normalized_weights).fillna(0.0)
    portfolio = portfolio[portfolio["weight"] > 1e-12].copy()
    total = float(portfolio["weight"].sum())
    if total > 1e-12:
        portfolio["weight"] = portfolio["weight"] / total
    return portfolio


def run_white_box_risk(
    predictions_csv: str | Path,
    *,
    output_dir: str | Path = "",
    model_name: str = "",
    score_column: str = "",
    metadata_csv: str = "",
    rebalance_step: int = 0,
    top_k: int = 5,
    min_score: float = float("-inf"),
    min_confidence: float = 0.0,
    require_positive_label: bool = False,
    min_close: float = 0.0,
    max_close: float = 0.0,
    min_amount: float = 0.0,
    min_turnover: float = 0.0,
    min_volume: float = 0.0,
    group_column: str = "",
    max_per_group: int = 0,
    secondary_group_column: str = "",
    secondary_max_per_group: int = 0,
    weighting: str = "equal",
    max_position_weight: float = 1.0,
    transaction_cost_bps: float = 10.0,
    hold_buffer: float = 0.0,
    max_turnover: float = 0.0,
    min_trade_weight: float = 0.0,
) -> dict[str, object]:
    signals = load_signal_frame(predictions_csv, model_name=model_name, score_column=score_column)
    if metadata_csv:
        signals = merge_metadata(signals, metadata_csv)
    signals = ensure_group_columns(signals, [group_column, secondary_group_column])
    signals = apply_liquidity_filters(
        signals,
        min_close=min_close,
        max_close=max_close,
        min_amount=min_amount,
        min_turnover=min_turnover,
        min_volume=min_volume,
    )

    if signals.empty:
        raise ValueError("No signals remain after metadata merge and liquidity filters.")

    rebalance_step = rebalance_step or int(signals["horizon"].iloc[0])
    dates = sorted(signals["date"].dt.strftime("%Y-%m-%d").unique())
    rebalance_dates = dates[:: max(rebalance_step, 1)]

    periods: list[dict[str, object]] = []
    positions: list[pd.DataFrame] = []
    actions: list[pd.DataFrame] = []
    equity = 1.0
    benchmark_equity = 1.0
    previous_weights: dict[str, float] = {}
    cost_rate = transaction_cost_bps / 10000.0

    for rebalance_date in rebalance_dates:
        date_slice = signals[signals["date"].dt.strftime("%Y-%m-%d") == rebalance_date].copy()
        eligible = apply_signal_guards(
            date_slice,
            min_score=min_score,
            min_confidence=min_confidence,
            require_positive_label=require_positive_label,
        )
        if eligible.empty:
            continue

        selected = select_with_hysteresis(
            eligible,
            top_k=top_k,
            group_column=group_column,
            max_per_group=max_per_group,
            secondary_group_column=secondary_group_column,
            secondary_max_per_group=secondary_max_per_group,
            previous_weights=previous_weights,
            hold_buffer=hold_buffer,
        )
        if selected.empty:
            continue

        sized = compute_position_weights(
            selected,
            weighting=weighting,
            score_column="score",
            confidence_column="confidence",
            max_position_weight=max_position_weight,
        )
        target_weights = {
            row["symbol"]: float(row["weight"])
            for _, row in sized[["symbol", "weight"]].iterrows()
        }
        desired_turnover = portfolio_turnover(previous_weights, target_weights)
        current_weights = blend_toward_target(
            previous_weights,
            target_weights,
            max_turnover=max_turnover,
        )
        current_weights = apply_min_trade_weight(
            previous_weights,
            current_weights,
            min_trade_weight=min_trade_weight,
        )
        sized = build_weighted_portfolio(date_slice, current_weights)
        if sized.empty:
            continue

        turnover = portfolio_turnover(previous_weights, current_weights)
        cost = turnover * cost_rate

        has_realized_return = bool(sized["realized_return"].notna().any())
        if has_realized_return:
            realized = sized["realized_return"].fillna(0.0)
            benchmark_realized = date_slice["realized_return"].dropna()
            gross_return = float((sized["weight"] * realized).sum())
            net_return = gross_return - cost
            benchmark_return = float(benchmark_realized.mean()) if not benchmark_realized.empty else 0.0
            equity *= 1 + net_return
            benchmark_equity *= 1 + benchmark_return
        else:
            gross_return = 0.0
            net_return = 0.0
            benchmark_return = 0.0

        action_df = build_rebalance_actions(rebalance_date, sized, previous_weights)
        selected_actions = action_df[action_df["target_weight"] > 0][
            ["symbol", "previous_weight", "target_weight", "weight_change", "action"]
        ].copy()
        sized = sized.merge(selected_actions, on="symbol", how="left")
        sized["rebalance_date"] = rebalance_date
        sized["transaction_cost"] = cost
        sized["turnover"] = turnover
        positions.append(sized)
        actions.append(action_df)

        periods.append(
            {
                "rebalance_date": rebalance_date,
                "selected_count": int(len(sized)),
                "mean_score": float(sized["score"].mean()),
                "mean_confidence": float(sized["confidence"].mean()),
                "gross_period_return": gross_return,
                "transaction_cost": cost,
                "desired_turnover": desired_turnover,
                "turnover": turnover,
                "turnover_reduction": max(desired_turnover - turnover, 0.0),
                "period_return": net_return,
                "benchmark_return": benchmark_return,
                "excess_return": net_return - benchmark_return,
                "equity": equity,
                "benchmark_equity": benchmark_equity,
                "return_available": has_realized_return,
                "open_count": int((action_df["action"] == "open").sum()),
                "add_count": int((action_df["action"] == "add").sum()),
                "reduce_count": int((action_df["action"] == "reduce").sum()),
                "hold_count": int((action_df["action"] == "hold").sum()),
                "exit_count": int((action_df["action"] == "exit").sum()),
                "gross_added_weight": float(action_df["weight_change"].clip(lower=0).sum()),
                "gross_reduced_weight": float(
                    -action_df["weight_change"].clip(upper=0).sum()
                ),
            }
        )
        previous_weights = current_weights

    if not periods:
        raise ValueError("Risk pipeline did not produce any rebalance periods.")

    periods_df = pd.DataFrame(periods)
    positions_df = pd.concat(positions, ignore_index=True) if positions else pd.DataFrame()
    actions_df = pd.concat(actions, ignore_index=True) if actions else pd.DataFrame()
    rebalances_per_year = 252 / max(rebalance_step, 1)
    total_return = float(periods_df["equity"].iloc[-1] - 1)
    benchmark_total_return = float(periods_df["benchmark_equity"].iloc[-1] - 1)

    summary = {
        "predictions_csv": str(predictions_csv),
        "model_name": str(signals["model_name"].iloc[0]),
        "model_mode": str(signals["model_mode"].iloc[0]),
        "horizon": int(signals["horizon"].iloc[0]),
        "top_k": top_k,
        "rebalance_step": rebalance_step,
        "min_score": min_score,
        "min_confidence": min_confidence,
        "weighting": weighting,
        "max_position_weight": max_position_weight,
        "transaction_cost_bps": transaction_cost_bps,
        "hold_buffer": hold_buffer,
        "max_turnover": max_turnover,
        "min_trade_weight": min_trade_weight,
        "group_column": group_column,
        "max_per_group": max_per_group,
        "secondary_group_column": secondary_group_column,
        "secondary_max_per_group": secondary_max_per_group,
        "periods": int(len(periods_df)),
        "total_return": total_return,
        "benchmark_total_return": benchmark_total_return,
        "excess_total_return": total_return - benchmark_total_return,
        "mean_period_return": float(periods_df["period_return"].mean()),
        "mean_gross_period_return": float(periods_df["gross_period_return"].mean()),
        "mean_benchmark_return": float(periods_df["benchmark_return"].mean()),
        "mean_desired_turnover": float(periods_df["desired_turnover"].mean()),
        "mean_turnover": float(periods_df["turnover"].mean()),
        "mean_turnover_reduction": float(periods_df["turnover_reduction"].mean()),
        "turnover_budget_binding_rate": float(
            (periods_df["desired_turnover"] - periods_df["turnover"] > 1e-9).mean()
        ),
        "total_transaction_cost": float(periods_df["transaction_cost"].sum()),
        "win_rate": float((periods_df["period_return"] > 0).mean()),
        "benchmark_win_rate": float((periods_df["benchmark_return"] > 0).mean()),
        "max_drawdown": max_drawdown(periods_df["equity"]),
        "benchmark_max_drawdown": max_drawdown(periods_df["benchmark_equity"]),
        "total_open_actions": int((actions_df["action"] == "open").sum()),
        "total_add_actions": int((actions_df["action"] == "add").sum()),
        "total_reduce_actions": int((actions_df["action"] == "reduce").sum()),
        "total_hold_actions": int((actions_df["action"] == "hold").sum()),
        "total_exit_actions": int((actions_df["action"] == "exit").sum()),
        "mean_open_actions": float(periods_df["open_count"].mean()),
        "mean_add_actions": float(periods_df["add_count"].mean()),
        "mean_reduce_actions": float(periods_df["reduce_count"].mean()),
        "mean_exit_actions": float(periods_df["exit_count"].mean()),
        "total_added_weight": float(actions_df["weight_change"].clip(lower=0).sum()),
        "total_reduced_weight": float(-actions_df["weight_change"].clip(upper=0).sum()),
        "mean_gross_added_weight": float(periods_df["gross_added_weight"].mean()),
        "mean_gross_reduced_weight": float(periods_df["gross_reduced_weight"].mean()),
        "annualized_return": annualized_return(total_return, len(periods_df), rebalances_per_year),
        "benchmark_annualized_return": annualized_return(
            benchmark_total_return, len(periods_df), rebalances_per_year
        ),
    }

    output_dir = Path(output_dir) if output_dir else Path(predictions_csv).parent / "white_box_risk"
    output_dir.mkdir(parents=True, exist_ok=True)
    periods_df.to_csv(output_dir / "risk_periods.csv", index=False, encoding="utf-8")
    positions_df.to_csv(output_dir / "risk_positions.csv", index=False, encoding="utf-8")
    actions_df.to_csv(output_dir / "risk_actions.csv", index=False, encoding="utf-8")
    (output_dir / "risk_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return {
        "periods_path": output_dir / "risk_periods.csv",
        "positions_path": output_dir / "risk_positions.csv",
        "actions_path": output_dir / "risk_actions.csv",
        "summary_path": output_dir / "risk_summary.json",
        "summary": summary,
    }
