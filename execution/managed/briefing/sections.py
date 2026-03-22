from __future__ import annotations

import json
import math
import sqlite3
from pathlib import Path
from typing import Any, Mapping, Sequence

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[3]
ENSEMBLE_ARTIFACT_ROOT = PROJECT_ROOT / "model_prediction" / "ensemble" / "artifacts"
DEFAULT_EXPERT_ORDER = ["lightgbm", "xgboost", "catboost", "lstm", "transformer", "ensemble"]


def load_source_frame(source_path: Path | None) -> pd.DataFrame:
    if source_path is None or not source_path.exists():
        return pd.DataFrame()
    try:
        frame = pd.read_csv(source_path, encoding="utf-8-sig")
    except Exception:
        return pd.DataFrame()
    if frame.empty:
        return frame
    if "date" in frame.columns:
        frame["date"] = frame["date"].astype(str)
    if "symbol" in frame.columns:
        frame["symbol"] = frame["symbol"].astype(str).str.upper()
    return frame


def infer_model_name_hint(source_frame: pd.DataFrame, *, strategy_id: str) -> str:
    if not source_frame.empty and "model_name" in source_frame.columns:
        model_series = source_frame["model_name"].dropna().astype(str)
        if not model_series.empty:
            return str(model_series.iloc[-1]).strip() or strategy_id
    return strategy_id


def build_symbol_price_curves(
    *,
    source_frame: pd.DataFrame,
    symbols: Sequence[str],
    up_to_date: str,
    lookback: int,
) -> dict[str, list[dict[str, Any]]]:
    if source_frame.empty or "date" not in source_frame.columns or "close" not in source_frame.columns:
        return {}
    frame = source_frame.copy()
    frame["date"] = frame["date"].astype(str)
    frame["symbol"] = frame.get("symbol", "").astype(str).str.upper()
    frame["close"] = pd.to_numeric(frame["close"], errors="coerce")
    frame = frame.dropna(subset=["close"])
    if up_to_date:
        frame = frame[frame["date"] <= str(up_to_date)]
    if frame.empty:
        return {}

    result: dict[str, list[dict[str, Any]]] = {}
    for raw_symbol in symbols:
        symbol = str(raw_symbol or "").upper().strip()
        if not symbol:
            continue
        sub = frame[frame["symbol"] == symbol].sort_values("date").tail(max(8, int(lookback)))
        if len(sub) < 2:
            continue
        first_close = float(sub["close"].iloc[0])
        if first_close <= 0:
            continue
        points: list[dict[str, Any]] = []
        for _, row in sub.iterrows():
            close = float(row["close"])
            normalized = close / first_close
            points.append(
                {
                    "date": str(row["date"]),
                    "close": close,
                    "normalized_close": normalized,
                    "return_pct": normalized - 1.0,
                }
            )
        result[symbol] = points
    return result


def build_current_distribution(
    *,
    account_snapshot: Mapping[str, Any],
    positions_snapshot: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    distribution: list[dict[str, Any]] = []
    positions = [dict(item) for item in positions_snapshot if isinstance(item, Mapping)]
    for position in positions:
        symbol = str(position.get("symbol", "")).upper().strip()
        market_value = _to_float(position.get("market_value"), default=0.0)
        if not symbol or abs(market_value) < 1e-6:
            continue
        distribution.append({"label": symbol, "value": abs(market_value)})
    distribution.sort(key=lambda item: float(item["value"]), reverse=True)

    cash = _to_float(account_snapshot.get("cash"), default=0.0)
    if cash > 0:
        distribution.append({"label": "现金", "value": cash})
    if not distribution:
        buying_power = _to_float(account_snapshot.get("buying_power"), default=0.0)
        if buying_power > 0:
            distribution.append({"label": "现金", "value": buying_power})
    return distribution


def load_equity_curve(ledger_path_value: Any) -> list[dict[str, Any]]:
    ledger_path = _resolve_path(ledger_path_value)
    if ledger_path is None or not ledger_path.exists():
        return []
    try:
        conn = sqlite3.connect(ledger_path)
    except Exception:
        return []
    try:
        rows = conn.execute(
            """
            SELECT session_date, timestamp_utc, equity
            FROM equity_snapshots
            ORDER BY timestamp_utc ASC
            """
        ).fetchall()
    except Exception:
        conn.close()
        return []
    conn.close()
    if not rows:
        return []

    latest_by_session: dict[str, tuple[str, float]] = {}
    for session_date, timestamp_utc, equity in rows:
        date_key = str(session_date or "").strip()
        if not date_key:
            timestamp_text = str(timestamp_utc or "").strip()
            if len(timestamp_text) >= 10:
                date_key = timestamp_text[:10]
        if not date_key:
            continue
        ts_key = str(timestamp_utc or "").strip()
        equity_value = float(equity or 0.0)
        previous = latest_by_session.get(date_key)
        if previous is None or ts_key >= previous[0]:
            # 每个交易日仅保留最新权益快照。
            latest_by_session[date_key] = (ts_key, equity_value)

    ordered_dates = sorted(latest_by_session.keys())[-14:]
    ordered = [
        {
            "date": date_key,
            "timestamp_utc": latest_by_session[date_key][0],
            "equity": latest_by_session[date_key][1],
        }
        for date_key in ordered_dates
    ]

    if not ordered:
        return []
    base = ordered[0]["equity"] if ordered[0]["equity"] > 0 else 1.0
    for item in ordered:
        item["pnl_pct"] = (item["equity"] / base) - 1.0
    return ordered


def select_submit_curve_symbols(
    *,
    positions_snapshot: Sequence[Mapping[str, Any]],
    top_symbols: Sequence[str],
    max_count: int,
) -> list[str]:
    ordered: list[str] = []
    positions = [dict(item) for item in positions_snapshot if isinstance(item, Mapping)]
    ranked_positions = sorted(
        positions,
        key=lambda item: abs(_to_float(item.get("market_value"), default=0.0)),
        reverse=True,
    )
    for item in ranked_positions:
        symbol = str(item.get("symbol", "")).upper().strip()
        if symbol and symbol not in ordered:
            ordered.append(symbol)
        if len(ordered) >= max_count:
            return ordered
    for raw_symbol in top_symbols:
        symbol = str(raw_symbol or "").upper().strip()
        if symbol and symbol not in ordered:
            ordered.append(symbol)
        if len(ordered) >= max_count:
            break
    return ordered


def build_expected_projection(
    *,
    source_frame: pd.DataFrame,
    top_positions: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    slope = 0.0
    intercept = 0.0
    model_quality = "insufficient"
    if (
        not source_frame.empty
        and "score" in source_frame.columns
        and "realized_return" in source_frame.columns
    ):
        train = source_frame[["score", "realized_return"]].copy()
        train["score"] = pd.to_numeric(train["score"], errors="coerce")
        train["realized_return"] = pd.to_numeric(train["realized_return"], errors="coerce")
        train = train.dropna()
        if len(train) >= 30:
            x = train["score"].astype(float)
            y = train["realized_return"].astype(float)
            x_mean = float(x.mean())
            y_mean = float(y.mean())
            var_x = float(((x - x_mean) ** 2).mean())
            if var_x > 1e-9:
                cov_xy = float(((x - x_mean) * (y - y_mean)).mean())
                slope = cov_xy / var_x
                intercept = y_mean - slope * x_mean
                model_quality = "ok"
            else:
                intercept = y_mean
                model_quality = "flat"

    contributions: list[dict[str, Any]] = []
    for item in top_positions:
        symbol = str(item.get("symbol", "")).upper().strip()
        weight = _to_float(item.get("target_weight"), default=0.0)
        score = _to_float(item.get("score"), default=0.0)
        if not symbol or weight <= 0:
            continue
        expected_return = intercept + slope * score
        expected_return = max(-0.20, min(0.20, expected_return))
        contributions.append(
            {
                "symbol": symbol,
                "weight": weight,
                "score": score,
                "expected_return": expected_return,
                "contribution": weight * expected_return,
            }
        )
    contributions.sort(key=lambda item: abs(float(item["contribution"])), reverse=True)
    expected_portfolio_return = float(sum(float(item["contribution"]) for item in contributions))

    trend_curve: list[dict[str, Any]] = []
    floor = max(-0.95, expected_portfolio_return)
    for day in range(0, 6):
        scaled = (day / 5.0) if day > 0 else 0.0
        projected = ((1.0 + floor) ** scaled) - 1.0
        trend_curve.append({"day": day, "portfolio_return": projected})

    return {
        "model_quality": model_quality,
        "regression": {"slope": slope, "intercept": intercept},
        "expected_portfolio_return": expected_portfolio_return,
        "contributions": contributions[:6],
        "trend_curve": trend_curve,
    }


def build_research_conclusion(
    *,
    top_positions: Sequence[Mapping[str, Any]],
    expert_snapshot: Mapping[str, Any],
) -> str:
    if not top_positions:
        return "本轮没有形成有效仓位信号。"
    top = dict(top_positions[0])
    top_symbol = str(top.get("symbol", "")).upper() or "N/A"
    top_weight = (_to_float(top.get("target_weight"), default=0.0)) * 100.0
    agreement = _to_float(expert_snapshot.get("agreement_ratio"), default=0.0)
    if agreement >= 0.75:
        mood = "专家共识偏强"
    elif agreement >= 0.5:
        mood = "专家共识中性偏多"
    else:
        mood = "专家分歧较大，建议控仓"
    return f"当前核心仓位偏向 {top_symbol}（{top_weight:.1f}%），{mood}。"


def build_expert_snapshot(
    *,
    strategy_id: str,
    model_name_hint: str,
    rebalance_date: str,
    symbols: Sequence[str],
) -> dict[str, Any]:
    symbols_norm = [str(item or "").upper().strip() for item in symbols if str(item or "").strip()]
    if not symbols_norm:
        return {}
    manifest_path = _find_ensemble_manifest(
        strategy_id=strategy_id,
        model_name_hint=model_name_hint,
    )
    if manifest_path is None:
        return {}

    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception:
        return {}

    source_metadata = manifest.get("source_metadata")
    expert_paths: dict[str, Path] = {}
    if isinstance(source_metadata, list):
        for item in source_metadata:
            if not isinstance(item, Mapping):
                continue
            model_name = str(item.get("model_name", "")).lower().strip()
            csv_path = _resolve_path(item.get("prediction_csv"))
            if model_name and csv_path is not None and csv_path.exists():
                expert_paths[model_name] = csv_path

    ensemble_csv = manifest_path.parent / "test_predictions.csv"
    if ensemble_csv.exists():
        expert_paths["ensemble"] = ensemble_csv

    if not expert_paths:
        return {}

    asof_date = str(rebalance_date or "").strip()
    if not asof_date:
        asof_date = _infer_latest_date(next(iter(expert_paths.values())))

    scores: dict[str, dict[str, float | None]] = {}
    for expert_name, csv_path in expert_paths.items():
        scores[expert_name] = _extract_scores_for_symbols(
            csv_path=csv_path,
            symbols=symbols_norm,
            date_value=asof_date,
        )

    experts = [name for name in DEFAULT_EXPERT_ORDER if name in scores]
    if not experts:
        experts = list(scores.keys())

    agreement_ratio = _compute_expert_agreement_ratio(
        scores=scores,
        symbols=symbols_norm,
    )

    return {
        "asof_date": asof_date,
        "symbols": symbols_norm,
        "experts": experts,
        "scores": scores,
        "agreement_ratio": agreement_ratio,
        "manifest_path": str(manifest_path),
    }


def _compute_expert_agreement_ratio(*, scores: Mapping[str, Mapping[str, float | None]], symbols: Sequence[str]) -> float:
    if "ensemble" not in scores:
        return 0.0
    matches = 0
    total = 0
    for symbol in symbols:
        ensemble_value = _to_float(scores["ensemble"].get(symbol), default=None)
        if ensemble_value is None:
            continue
        ensemble_sign = 1 if ensemble_value >= 0 else -1
        for expert_name, symbol_map in scores.items():
            if expert_name == "ensemble":
                continue
            value = _to_float(symbol_map.get(symbol), default=None)
            if value is None:
                continue
            total += 1
            if (1 if value >= 0 else -1) == ensemble_sign:
                matches += 1
    if total <= 0:
        return 0.0
    return matches / total


def _extract_scores_for_symbols(*, csv_path: Path, symbols: Sequence[str], date_value: str) -> dict[str, float | None]:
    try:
        frame = pd.read_csv(csv_path, encoding="utf-8-sig")
    except Exception:
        return {symbol: None for symbol in symbols}
    if frame.empty or "symbol" not in frame.columns:
        return {symbol: None for symbol in symbols}
    frame["symbol"] = frame["symbol"].astype(str).str.upper()
    if "date" in frame.columns:
        frame["date"] = frame["date"].astype(str)
        if date_value:
            frame = frame[frame["date"] == date_value]
        if frame.empty:
            date_value = _infer_latest_date_from_frame(frame=pd.read_csv(csv_path, encoding="utf-8-sig"))
            frame = pd.read_csv(csv_path, encoding="utf-8-sig")
            frame["symbol"] = frame["symbol"].astype(str).str.upper()
            frame["date"] = frame["date"].astype(str)
            frame = frame[frame["date"] == date_value]

    score_column = _choose_score_column(frame)
    if not score_column:
        return {symbol: None for symbol in symbols}

    frame[score_column] = pd.to_numeric(frame[score_column], errors="coerce")
    result = {}
    for symbol in symbols:
        sub = frame[frame["symbol"] == symbol]
        if sub.empty:
            result[symbol] = None
            continue
        result[symbol] = _to_float(sub.iloc[-1][score_column], default=None)
    return result


def _choose_score_column(frame: pd.DataFrame) -> str:
    for column in ("pred_score", "pred_return", "prediction", "score"):
        if column in frame.columns:
            return column
    return ""


def _infer_latest_date(csv_path: Path) -> str:
    try:
        frame = pd.read_csv(csv_path, encoding="utf-8-sig")
    except Exception:
        return ""
    return _infer_latest_date_from_frame(frame=frame)


def _infer_latest_date_from_frame(*, frame: pd.DataFrame) -> str:
    if "date" not in frame.columns or frame.empty:
        return ""
    dates = frame["date"].dropna().astype(str)
    return str(dates.max()) if not dates.empty else ""


def _find_ensemble_manifest(*, strategy_id: str, model_name_hint: str) -> Path | None:
    if not ENSEMBLE_ARTIFACT_ROOT.exists():
        return None
    manifests = list(ENSEMBLE_ARTIFACT_ROOT.glob("**/ensemble_manifest.json"))
    if not manifests:
        return None

    aliases = _strategy_aliases(strategy_id=strategy_id, model_name_hint=model_name_hint)
    ranked: list[tuple[int, float, Path]] = []
    for path in manifests:
        parent_name = path.parent.name.lower()
        score = 0
        if parent_name == model_name_hint.lower():
            score += 8
        if parent_name == strategy_id.lower():
            score += 7
        if parent_name in aliases:
            score += 6
        for alias in aliases:
            if alias in parent_name:
                score += 2
        ranked.append((score, path.stat().st_mtime, path))
    ranked.sort(key=lambda item: (item[0], item[1]), reverse=True)
    return ranked[0][2]


def _strategy_aliases(*, strategy_id: str, model_name_hint: str) -> set[str]:
    aliases = {strategy_id.lower(), model_name_hint.lower()}
    if "zeroshot" in strategy_id.lower():
        aliases.add("us_zeroshot_a_share_multi_daily")
        aliases.add("us_zeroshot_a_share_multi_expert_daily")
    if "us_full" in strategy_id.lower():
        aliases.add("us_full_multi_expert_daily")
        aliases.add("us_full_multi_daily")
        aliases.add("us_full_train")
    return {item for item in aliases if item}


def _resolve_path(path_value: Any) -> Path | None:
    if path_value in (None, ""):
        return None
    path = Path(str(path_value))
    return path if path.is_absolute() else PROJECT_ROOT / path


def _to_float(value: Any, *, default: float | None) -> float | None:
    if value in (None, ""):
        return default
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return default
    if math.isnan(numeric):
        return default
    return numeric
