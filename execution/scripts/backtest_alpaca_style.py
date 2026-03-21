#!/usr/bin/env python3
"""Replay a risk_positions strategy through Alpaca-style execution sizing."""

from __future__ import annotations

import argparse
import json
import math
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

from data_module.common.stock_schema import normalize_dataframe
from execution.common.execution_models import ExecutionPlan, PositionSnapshot, TargetPosition
from execution.common.order_safety import validate_execution_plan
from execution.common.reconciliation import build_order_intents, normalize_current_weights


@dataclass(slots=True)
class ExecutedOrder:
    rebalance_date: str
    symbol: str
    side: str
    submit_as: str
    desired_notional: float
    desired_qty: float
    executed_notional: float
    executed_qty: float
    execution_price: float
    cash_before: float
    cash_after: float
    reason: str
    status: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Backtest a white-box risk strategy with Alpaca-style execution sizing."
    )
    parser.add_argument("strategy_config", help="Path to a strategy JSON config.")
    parser.add_argument(
        "--universe-csv",
        default="",
        help="Normalized U.S. universe CSV used to mark positions and derive execution prices.",
    )
    parser.add_argument(
        "--output-dir",
        default="",
        help="Directory used to store execution backtest artifacts.",
    )
    parser.add_argument(
        "--initial-equity",
        type=float,
        default=0.0,
        help="Optional starting equity override.",
    )
    return parser.parse_args()


def load_json(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def load_strategy_config(path: str | Path) -> tuple[dict[str, Any], Path]:
    config_path = Path(path)
    config = json.loads(config_path.read_text(encoding="utf-8"))
    return config, config_path


def resolve_path(value: str | Path, *, base_dir: Path) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    base_candidate = (base_dir / path).resolve()
    if base_candidate.exists():
        return base_candidate
    project_candidate = (PROJECT_ROOT / path).resolve()
    if project_candidate.exists():
        return project_candidate
    return project_candidate


def default_us_universe_csv() -> Path:
    candidates = [
        PROJECT_ROOT
        / "data"
        / "interim"
        / "stooq"
        / "universes"
        / "us_large_cap_30_20200101_20251231_hfq_normalized.csv",
        PROJECT_ROOT
        / "data"
        / "interim"
        / "stooq"
        / "universes"
        / "us_large_cap_30_20200101_20260320_hfq_normalized.csv",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    raise FileNotFoundError("Could not find a default U.S. universe CSV for Alpaca-style backtest.")


def runtime_dir(strategy_id: str, override: str = "") -> Path:
    if override:
        return Path(override)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return PROJECT_ROOT / "execution" / "experiments" / strategy_id / stamp


def normalize_buffer(raw_value: object) -> float:
    try:
        value = float(raw_value)
    except (TypeError, ValueError):
        value = 1.0
    return min(max(value, 0.0), 1.0)


def load_risk_positions(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path, encoding="utf-8-sig")
    if df.empty:
        raise ValueError(f"risk_positions.csv is empty: {path}")
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df["rebalance_date"] = pd.to_datetime(df["rebalance_date"], errors="coerce")
    for column in [
        "close",
        "score",
        "confidence",
        "target_weight",
        "previous_weight",
        "realized_return",
    ]:
        if column in df.columns:
            df[column] = pd.to_numeric(df[column], errors="coerce")
    return df.sort_values(["rebalance_date", "symbol"], kind="stable").reset_index(drop=True)


def load_risk_periods(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    df = pd.read_csv(path, encoding="utf-8-sig")
    if "rebalance_date" in df.columns:
        df["rebalance_date"] = pd.to_datetime(df["rebalance_date"], errors="coerce")
    return df


def load_universe(path: Path) -> pd.DataFrame:
    raw_df = pd.read_csv(path, encoding="utf-8-sig")
    universe = normalize_dataframe(raw_df)
    universe["date"] = pd.to_datetime(universe["date"], errors="coerce")
    for column in ["open", "high", "low", "close", "volume", "amount", "turnover"]:
        if column in universe.columns:
            universe[column] = pd.to_numeric(universe[column], errors="coerce")
    universe = universe.dropna(subset=["date", "symbol", "close"]).copy()
    return universe.sort_values(["symbol", "date"], kind="stable").reset_index(drop=True)


def build_price_lookup(universe_df: pd.DataFrame) -> dict[tuple[str, str], float]:
    working = universe_df.copy()
    working["date_str"] = working["date"].dt.strftime("%Y-%m-%d")
    return {
        (str(row["date_str"]), str(row["symbol"])): float(row["close"])
        for _, row in working[["date_str", "symbol", "close"]].iterrows()
    }


def lookup_price(
    price_lookup: dict[tuple[str, str], float],
    *,
    rebalance_date: str,
    symbol: str,
    fallback: float = 0.0,
) -> float:
    return float(price_lookup.get((rebalance_date, symbol), fallback) or fallback)


def build_target_positions(
    current_date_df: pd.DataFrame,
    *,
    holdings: dict[str, float],
    current_positions: list[PositionSnapshot],
    price_lookup: dict[tuple[str, str], float],
    rebalance_date_str: str,
) -> list[TargetPosition]:
    current_weight_map = {position.symbol: position.weight for position in current_positions}
    targets: list[TargetPosition] = []
    seen_symbols: set[str] = set()

    for _, row in current_date_df.iterrows():
        symbol = str(row["symbol"])
        seen_symbols.add(symbol)
        targets.append(
            TargetPosition(
                symbol=symbol,
                target_weight=float(row.get("target_weight", 0.0) or 0.0),
                previous_weight=float(current_weight_map.get(symbol, row.get("previous_weight", 0.0) or 0.0)),
                action=str(row.get("action", "")),
                reference_price=float(row.get("close", 0.0) or 0.0),
                score=float(row.get("score", 0.0) or 0.0),
                confidence=float(row.get("confidence", 0.0) or 0.0),
                rebalance_date=rebalance_date_str,
                metadata={
                    "model_mode": row.get("model_mode", ""),
                    "industry_group": row.get("industry_group", ""),
                    "name": row.get("name", ""),
                },
            )
        )

    for symbol, qty in holdings.items():
        if qty <= 1e-12 or symbol in seen_symbols:
            continue
        reference_price = lookup_price(
            price_lookup,
            rebalance_date=rebalance_date_str,
            symbol=symbol,
            fallback=0.0,
        )
        targets.append(
            TargetPosition(
                symbol=symbol,
                target_weight=0.0,
                previous_weight=float(current_weight_map.get(symbol, 0.0)),
                action="exit",
                reference_price=reference_price,
                score=0.0,
                confidence=0.0,
                rebalance_date=rebalance_date_str,
                metadata={},
            )
        )

    return targets


def apply_execution_weight_cap(df: pd.DataFrame, *, max_position_weight: float) -> tuple[pd.DataFrame, int]:
    working = df.copy()
    if max_position_weight <= 0 or "target_weight" not in working.columns:
        return working, 0
    original = pd.to_numeric(working["target_weight"], errors="coerce").fillna(0.0)
    clipped = original.clip(lower=0.0, upper=max_position_weight)
    adjustment_count = int((original != clipped).sum())
    working["target_weight"] = clipped
    return working, adjustment_count


def build_current_positions(
    holdings: dict[str, float],
    *,
    rebalance_date_str: str,
    price_lookup: dict[tuple[str, str], float],
    account_equity: float,
) -> list[PositionSnapshot]:
    positions: list[PositionSnapshot] = []
    for symbol, qty in sorted(holdings.items()):
        if qty <= 1e-12:
            continue
        price = lookup_price(price_lookup, rebalance_date=rebalance_date_str, symbol=symbol)
        if price <= 0:
            continue
        market_value = qty * price
        positions.append(
            PositionSnapshot(
                symbol=symbol,
                qty=qty,
                market_value=market_value,
                current_price=price,
            )
        )
    return normalize_current_weights(positions, account_equity=account_equity)


def quantize_qty(qty: float, *, allow_fractional: bool) -> float:
    if qty <= 0:
        return 0.0
    if allow_fractional:
        return float(qty)
    return float(math.floor(qty))


def execute_orders(
    plan: ExecutionPlan,
    *,
    holdings: dict[str, float],
    cash: float,
    price_lookup: dict[tuple[str, str], float],
    rebalance_date_str: str,
    transaction_cost_bps: float,
) -> tuple[dict[str, float], float, list[ExecutedOrder], float]:
    working_holdings = dict(holdings)
    executed_orders: list[ExecutedOrder] = []
    total_cost = 0.0
    cost_rate = transaction_cost_bps / 10000.0

    ordered_intents = sorted(plan.order_intents, key=lambda item: 0 if item.side == "sell" else 1)
    for intent in ordered_intents:
        price = lookup_price(
            price_lookup,
            rebalance_date=rebalance_date_str,
            symbol=intent.symbol,
            fallback=intent.reference_price,
        )
        if price <= 0:
            executed_orders.append(
                ExecutedOrder(
                    rebalance_date=rebalance_date_str,
                    symbol=intent.symbol,
                    side=intent.side,
                    submit_as=intent.submit_as,
                    desired_notional=float(abs(intent.delta_notional)),
                    desired_qty=float(intent.submit_qty or intent.estimated_qty),
                    executed_notional=0.0,
                    executed_qty=0.0,
                    execution_price=0.0,
                    cash_before=float(cash),
                    cash_after=float(cash),
                    reason=intent.reason,
                    status="skipped_no_price",
                )
            )
            continue

        cash_before = cash
        executed_qty = 0.0
        desired_notional = float(abs(intent.delta_notional))
        desired_qty = float(intent.submit_qty or intent.estimated_qty)

        if intent.side == "sell":
            available_qty = float(working_holdings.get(intent.symbol, 0.0))
            candidate_qty = intent.submit_qty if intent.submit_as == "qty" else desired_notional / price
            executed_qty = min(available_qty, quantize_qty(candidate_qty, allow_fractional=intent.allow_fractional))
            executed_notional = executed_qty * price
            cash += executed_notional
            working_holdings[intent.symbol] = max(available_qty - executed_qty, 0.0)
        else:
            desired_notional = intent.submit_notional if intent.submit_as == "notional" else desired_qty * price
            affordable_notional = min(max(cash, 0.0), max(desired_notional, 0.0))
            candidate_qty = affordable_notional / price if price > 0 else 0.0
            executed_qty = quantize_qty(candidate_qty, allow_fractional=intent.allow_fractional)
            executed_notional = executed_qty * price
            cash -= executed_notional
            working_holdings[intent.symbol] = float(working_holdings.get(intent.symbol, 0.0)) + executed_qty

        order_cost = executed_notional * cost_rate
        cash -= order_cost
        total_cost += order_cost

        if working_holdings.get(intent.symbol, 0.0) <= 1e-12:
            working_holdings.pop(intent.symbol, None)

        if executed_notional <= 1e-12:
            status = "skipped_unfilled"
        elif executed_notional + 1e-9 < desired_notional:
            status = "partial_fill"
        else:
            status = "filled"

        executed_orders.append(
            ExecutedOrder(
                rebalance_date=rebalance_date_str,
                symbol=intent.symbol,
                side=intent.side,
                submit_as=intent.submit_as,
                desired_notional=desired_notional,
                desired_qty=desired_qty,
                executed_notional=executed_notional,
                executed_qty=executed_qty,
                execution_price=price,
                cash_before=cash_before,
                cash_after=cash,
                reason=intent.reason,
                status=status,
            )
        )

    return working_holdings, cash, executed_orders, total_cost


def latest_rebalance_date(risk_positions_df: pd.DataFrame) -> str:
    return str(risk_positions_df["rebalance_date"].dt.strftime("%Y-%m-%d").max())


def next_rebalance_date(unique_dates: list[str], current_index: int) -> str | None:
    if current_index + 1 >= len(unique_dates):
        return None
    return unique_dates[current_index + 1]


def portfolio_market_value(
    holdings: dict[str, float],
    *,
    rebalance_date_str: str,
    price_lookup: dict[tuple[str, str], float],
) -> float:
    total = 0.0
    for symbol, qty in holdings.items():
        price = lookup_price(price_lookup, rebalance_date=rebalance_date_str, symbol=symbol)
        total += qty * price
    return float(total)


def period_end_equity(
    *,
    holdings: dict[str, float],
    cash: float,
    next_date: str | None,
    current_date_df: pd.DataFrame,
    price_lookup: dict[tuple[str, str], float],
    rebalance_date_str: str,
) -> float:
    if next_date:
        return cash + portfolio_market_value(holdings, rebalance_date_str=next_date, price_lookup=price_lookup)

    total = float(cash)
    return_map = {
        str(row["symbol"]): float(row.get("realized_return", 0.0) or 0.0)
        for _, row in current_date_df.iterrows()
    }
    for symbol, qty in holdings.items():
        current_price = lookup_price(price_lookup, rebalance_date=rebalance_date_str, symbol=symbol)
        total += qty * current_price * (1.0 + return_map.get(symbol, 0.0))
    return float(total)


def summary_metrics(equity_curve: pd.Series) -> tuple[float, float]:
    if equity_curve.empty:
        return 0.0, 0.0
    running_max = equity_curve.cummax()
    drawdown = equity_curve / running_max - 1.0
    return float(equity_curve.iloc[-1] / equity_curve.iloc[0] - 1.0), float(drawdown.min())


def annualized_return(total_return: float, periods: int, rebalance_step: int) -> float:
    if periods <= 0 or rebalance_step <= 0:
        return 0.0
    trading_days = periods * rebalance_step
    years = trading_days / 252.0
    if years <= 0:
        return 0.0
    return float((1.0 + total_return) ** (1.0 / years) - 1.0)


def benchmark_equity_from_periods(periods_df: pd.DataFrame) -> pd.Series:
    if periods_df.empty or "benchmark_return" not in periods_df.columns:
        return pd.Series(dtype=float)
    returns = pd.to_numeric(periods_df["benchmark_return"], errors="coerce").fillna(0.0)
    equity = (1.0 + returns).cumprod()
    return equity


def main() -> int:
    args = parse_args()
    config, config_path = load_strategy_config(args.strategy_config)
    strategy_id = str(config["strategy_id"])
    config_dir = config_path.parent
    source = dict(config.get("source", {}))
    execution = dict(config.get("execution", {}))
    if source.get("type") != "risk_positions_csv":
        raise ValueError("Only risk_positions_csv source is supported.")

    risk_positions_path = resolve_path(str(source["path"]), base_dir=config_dir)
    risk_summary_path = resolve_path(str(source.get("summary_path", "")), base_dir=config_dir)
    risk_periods_path = risk_positions_path.with_name("risk_periods.csv")
    universe_path = (
        resolve_path(args.universe_csv, base_dir=config_dir)
        if args.universe_csv
        else default_us_universe_csv()
    )
    output_dir = runtime_dir(strategy_id, args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    risk_positions_df = load_risk_positions(risk_positions_path)
    risk_periods_df = load_risk_periods(risk_periods_path)
    universe_df = load_universe(universe_path)
    price_lookup = build_price_lookup(universe_df)

    initial_equity = (
        float(args.initial_equity)
        if args.initial_equity > 0
        else float(execution.get("default_account_equity", 100000.0))
    )
    buying_power_buffer = normalize_buffer(execution.get("buying_power_buffer", 1.0))
    order_sizing_mode = str(execution.get("order_sizing_mode", "hybrid"))
    rebalance_dates = sorted(risk_positions_df["rebalance_date"].dt.strftime("%Y-%m-%d").unique().tolist())
    rebalance_step = int(execution.get("rebalance_step", 5) or 5)

    cash = float(initial_equity)
    holdings: dict[str, float] = {}
    periods_rows: list[dict[str, Any]] = []
    order_rows: list[dict[str, Any]] = []
    position_rows: list[dict[str, Any]] = []
    equity_value = float(initial_equity)
    weight_cap_adjustments = 0

    for index, rebalance_date_str in enumerate(rebalance_dates):
        current_date_df = risk_positions_df[
            risk_positions_df["rebalance_date"].dt.strftime("%Y-%m-%d") == rebalance_date_str
        ].copy()
        if current_date_df.empty:
            continue
        current_date_df, adjustment_count = apply_execution_weight_cap(
            current_date_df,
            max_position_weight=float(execution.get("max_position_weight", 0.0) or 0.0),
        )
        weight_cap_adjustments += adjustment_count

        account_equity = cash + portfolio_market_value(
            holdings,
            rebalance_date_str=rebalance_date_str,
            price_lookup=price_lookup,
        )
        current_positions = build_current_positions(
            holdings,
            rebalance_date_str=rebalance_date_str,
            price_lookup=price_lookup,
            account_equity=account_equity if account_equity > 0 else initial_equity,
        )
        targets = build_target_positions(
            current_date_df,
            holdings=holdings,
            current_positions=current_positions,
            price_lookup=price_lookup,
            rebalance_date_str=rebalance_date_str,
        )
        planning_equity = account_equity * buying_power_buffer
        order_intents = build_order_intents(
            targets,
            current_positions,
            account_equity=account_equity,
            planning_equity=planning_equity,
            allow_fractional=bool(execution.get("allow_fractional", True)),
            order_sizing_mode=order_sizing_mode,
            order_type=str(execution.get("order_type", "market")),
            time_in_force=str(execution.get("time_in_force", "day")),
        )
        plan = ExecutionPlan(
            strategy_id=strategy_id,
            broker=str(config.get("broker", "alpaca")),
            rebalance_date=rebalance_date_str,
            generated_at=datetime.now(timezone.utc).isoformat(),
            account_equity=account_equity,
            planning_equity=planning_equity,
            account_buying_power=cash,
            current_positions=current_positions,
            target_positions=targets,
            order_intents=order_intents,
            notes=[],
        )
        plan = validate_execution_plan(
            plan,
            max_position_weight=float(execution.get("max_position_weight", 1.0)),
            min_order_notional=float(execution.get("min_order_notional", 0.0)),
        )

        holdings, cash, executed_orders, transaction_cost = execute_orders(
            plan,
            holdings=holdings,
            cash=cash,
            price_lookup=price_lookup,
            rebalance_date_str=rebalance_date_str,
            transaction_cost_bps=float(current_date_df["transaction_cost"].iloc[0] * 10000.0)
            if "transaction_cost" in current_date_df.columns and pd.notna(current_date_df["transaction_cost"].iloc[0])
            else float(execution.get("transaction_cost_bps", 10.0)),
        )
        order_rows.extend([row.to_dict() for row in executed_orders])

        next_date = next_rebalance_date(rebalance_dates, index)
        end_equity = period_end_equity(
            holdings=holdings,
            cash=cash,
            next_date=next_date,
            current_date_df=current_date_df,
            price_lookup=price_lookup,
            rebalance_date_str=rebalance_date_str,
        )
        period_return = (end_equity / account_equity - 1.0) if account_equity > 0 else 0.0
        benchmark_row = pd.DataFrame()
        if not risk_periods_df.empty:
            benchmark_row = risk_periods_df[
                risk_periods_df["rebalance_date"].dt.strftime("%Y-%m-%d") == rebalance_date_str
            ]
        benchmark_return = (
            float(benchmark_row["benchmark_return"].iloc[0])
            if not benchmark_row.empty and "benchmark_return" in benchmark_row.columns
            else 0.0
        )

        equity_value = end_equity
        periods_rows.append(
            {
                "rebalance_date": rebalance_date_str,
                "selected_count": int((current_date_df["target_weight"] > 0).sum()),
                "account_equity_start": account_equity,
                "planning_equity": planning_equity,
                "cash_after_trade": cash,
                "transaction_cost": transaction_cost,
                "order_count": len(plan.order_intents),
                "filled_order_count": int(sum(1 for row in executed_orders if row.status == "filled")),
                "partial_fill_count": int(sum(1 for row in executed_orders if row.status == "partial_fill")),
                "period_return": period_return,
                "benchmark_return": benchmark_return,
                "equity": end_equity,
            }
        )

        current_price_map = {
            symbol: lookup_price(price_lookup, rebalance_date=next_date or rebalance_date_str, symbol=symbol)
            for symbol in holdings
        }
        denominator = end_equity if end_equity > 0 else 1.0
        for symbol, qty in sorted(holdings.items()):
            price = current_price_map.get(symbol, 0.0)
            market_value = qty * price
            position_rows.append(
                {
                    "rebalance_date": rebalance_date_str,
                    "valuation_date": next_date or rebalance_date_str,
                    "symbol": symbol,
                    "qty": qty,
                    "current_price": price,
                    "market_value": market_value,
                    "weight": market_value / denominator,
                }
            )

    periods_df = pd.DataFrame(periods_rows)
    orders_df = pd.DataFrame(order_rows)
    positions_df = pd.DataFrame(position_rows)
    periods_path = output_dir / "execution_periods.csv"
    orders_path = output_dir / "execution_orders.csv"
    positions_path = output_dir / "execution_positions.csv"
    periods_df.to_csv(periods_path, index=False, encoding="utf-8")
    orders_df.to_csv(orders_path, index=False, encoding="utf-8")
    positions_df.to_csv(positions_path, index=False, encoding="utf-8")

    benchmark_equity = benchmark_equity_from_periods(periods_df)
    if not periods_df.empty:
        equity_curve = pd.to_numeric(periods_df["equity"], errors="coerce").ffill()
        total_return, max_drawdown = summary_metrics(equity_curve)
        benchmark_total_return = (
            float(benchmark_equity.iloc[-1] - 1.0) if not benchmark_equity.empty else 0.0
        )
    else:
        total_return = 0.0
        max_drawdown = 0.0
        benchmark_total_return = 0.0

    source_summary = load_json(risk_summary_path) if risk_summary_path.exists() else {}
    summary = {
        "strategy_id": strategy_id,
        "description": config.get("description", ""),
        "strategy_config": str(config_path.resolve()),
        "risk_positions_csv": str(risk_positions_path),
        "risk_summary_path": str(risk_summary_path) if risk_summary_path.exists() else "",
        "universe_csv": str(universe_path),
        "initial_equity": initial_equity,
        "buying_power_buffer": buying_power_buffer,
        "order_sizing_mode": order_sizing_mode,
        "rebalance_count": int(len(periods_df)),
        "total_return": total_return,
        "benchmark_total_return": benchmark_total_return,
        "excess_total_return": total_return - benchmark_total_return,
        "max_drawdown": max_drawdown,
        "annualized_return": annualized_return(total_return, len(periods_df), rebalance_step),
        "mean_period_return": float(periods_df["period_return"].mean()) if not periods_df.empty else 0.0,
        "mean_transaction_cost": float(periods_df["transaction_cost"].mean()) if not periods_df.empty else 0.0,
        "total_transaction_cost": float(periods_df["transaction_cost"].sum()) if not periods_df.empty else 0.0,
        "filled_orders": int((orders_df["status"] == "filled").sum()) if not orders_df.empty else 0,
        "partial_fills": int((orders_df["status"] == "partial_fill").sum()) if not orders_df.empty else 0,
        "weight_cap_adjustments": weight_cap_adjustments,
        "source_risk_total_return": source_summary.get("total_return"),
        "source_risk_benchmark_total_return": source_summary.get("benchmark_total_return"),
        "periods_path": str(periods_path),
        "orders_path": str(orders_path),
        "positions_path": str(positions_path),
    }
    summary_path = output_dir / "execution_summary.json"
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"[OK] Execution periods: {periods_path}")
    print(f"[OK] Execution orders: {orders_path}")
    print(f"[OK] Execution positions: {positions_path}")
    print(f"[OK] Execution summary: {summary_path}")
    print(f"[INFO] Rebalances: {summary['rebalance_count']}")
    print(f"[INFO] Total return: {summary['total_return']:.4f}")
    print(f"[INFO] Benchmark total return: {summary['benchmark_total_return']:.4f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
