"""Position sizing rules for white-box risk."""

from __future__ import annotations

import numpy as np
import pandas as pd


def _normalized_positive(values: pd.Series) -> pd.Series:
    positive = values.clip(lower=0).astype(float)
    total = positive.sum()
    if total <= 0:
        return pd.Series([1.0 / len(values)] * len(values), index=values.index)
    return positive / total


def _apply_max_weight(weights: pd.Series, max_position_weight: float) -> pd.Series:
    if max_position_weight <= 0 or max_position_weight >= 1:
        return weights / weights.sum()

    adjusted = (weights.copy().astype(float) / max(weights.sum(), 1e-12)).clip(lower=0.0)
    for _ in range(10):
        capped = adjusted.clip(upper=max_position_weight)
        residual = 1.0 - capped.sum()
        if residual <= 1e-9:
            adjusted = capped
            break
        uncapped_mask = capped < max_position_weight - 1e-12
        if not uncapped_mask.any():
            # Infeasible case: too few names to satisfy the cap while fully invested.
            # Keep capped weights as-is (sum < 1.0) so remaining capital stays in cash.
            adjusted = capped
            break
        redistribute = adjusted[uncapped_mask]
        if redistribute.sum() <= 0:
            adjusted = capped
            break
        capped.loc[uncapped_mask] += residual * redistribute / redistribute.sum()
        adjusted = capped

    total = float(adjusted.sum())
    if total <= 1e-12:
        return weights / max(weights.sum(), 1e-12)
    return adjusted


def normalize_weight_dict(weights: dict[str, float], *, eps: float = 1e-12) -> dict[str, float]:
    positive = {
        str(symbol): float(weight)
        for symbol, weight in weights.items()
        if float(weight) > eps
    }
    total = sum(positive.values())
    if total <= eps:
        return {}
    # Keep explicit cash when weights sum to less than 1.0; only scale down if overweight.
    if total > 1.0 + eps:
        return {symbol: weight / total for symbol, weight in positive.items()}
    return positive


def cap_gross_exposure(
    weights: dict[str, float],
    *,
    max_gross_exposure: float = 1.0,
    eps: float = 1e-12,
) -> dict[str, float]:
    normalized = normalize_weight_dict(weights, eps=eps)
    if not normalized:
        return {}

    gross_cap = min(max(float(max_gross_exposure), 0.0), 1.0)
    if gross_cap <= eps:
        return {}

    total = float(sum(normalized.values()))
    if total <= gross_cap + eps:
        return normalized

    scale = gross_cap / total
    return {
        symbol: scaled
        for symbol, weight in normalized.items()
        if (scaled := float(weight) * scale) > eps
    }


def compute_position_weights(
    selected: pd.DataFrame,
    *,
    weighting: str = "equal",
    score_column: str = "score",
    confidence_column: str = "confidence",
    max_position_weight: float = 1.0,
) -> pd.DataFrame:
    if selected.empty:
        return selected.copy()

    working = selected.copy()
    if weighting == "equal":
        base = pd.Series([1.0] * len(working), index=working.index, dtype=float)
    elif weighting == "score":
        base = _normalized_positive(pd.to_numeric(working[score_column], errors="coerce").fillna(0))
    elif weighting == "confidence":
        base = _normalized_positive(
            pd.to_numeric(working[confidence_column], errors="coerce").fillna(0)
        )
    elif weighting == "score_confidence":
        score = pd.to_numeric(working[score_column], errors="coerce").fillna(0)
        confidence = pd.to_numeric(working[confidence_column], errors="coerce").fillna(0)
        base = _normalized_positive(score.clip(lower=0) * confidence.clip(lower=0))
    else:
        raise ValueError(f"Unsupported weighting mode: {weighting}")

    weights = _apply_max_weight(base, max_position_weight)
    working["weight"] = weights.values
    return working


def blend_toward_target(
    previous_weights: dict[str, float],
    target_weights: dict[str, float],
    *,
    max_turnover: float = 0.0,
) -> dict[str, float]:
    normalized_target = normalize_weight_dict(target_weights)
    if not normalized_target:
        return {}

    normalized_previous = normalize_weight_dict(previous_weights)
    if not normalized_previous or max_turnover <= 0:
        return normalized_target

    desired_turnover = portfolio_turnover(normalized_previous, normalized_target)
    if desired_turnover <= max_turnover + 1e-12:
        return normalized_target

    blend_ratio = max_turnover / desired_turnover
    blended: dict[str, float] = {}
    for symbol in set(normalized_previous) | set(normalized_target):
        previous_weight = normalized_previous.get(symbol, 0.0)
        target_weight = normalized_target.get(symbol, 0.0)
        weight = previous_weight + blend_ratio * (target_weight - previous_weight)
        if weight > 1e-12:
            blended[str(symbol)] = float(weight)
    return normalize_weight_dict(blended)


def apply_min_trade_weight(
    previous_weights: dict[str, float],
    target_weights: dict[str, float],
    *,
    min_trade_weight: float = 0.0,
) -> dict[str, float]:
    normalized_target = normalize_weight_dict(target_weights)
    if min_trade_weight <= 0 or not previous_weights:
        return normalized_target

    normalized_previous = normalize_weight_dict(previous_weights)
    if not normalized_previous:
        return normalized_target

    locked_weights: dict[str, float] = {}
    flex_weights: dict[str, float] = {}
    all_symbols = set(normalized_previous) | set(normalized_target)
    for symbol in all_symbols:
        previous_weight = normalized_previous.get(symbol, 0.0)
        target_weight = normalized_target.get(symbol, 0.0)
        if abs(target_weight - previous_weight) < min_trade_weight:
            if previous_weight > 1e-12:
                locked_weights[str(symbol)] = previous_weight
        elif target_weight > 1e-12:
            flex_weights[str(symbol)] = target_weight

    locked_total = sum(locked_weights.values())
    if locked_total >= 1.0 - 1e-12:
        return normalize_weight_dict(locked_weights)

    flex_total = sum(flex_weights.values())
    if flex_total <= 1e-12:
        return normalize_weight_dict(locked_weights)

    residual = 1.0 - locked_total
    adjusted = dict(locked_weights)
    for symbol, weight in flex_weights.items():
        adjusted[symbol] = residual * weight / flex_total
    return normalize_weight_dict(adjusted)


def portfolio_turnover(
    previous_weights: dict[str, float], current_weights: dict[str, float]
) -> float:
    all_symbols = set(previous_weights) | set(current_weights)
    gross_change = sum(
        abs(current_weights.get(symbol, 0.0) - previous_weights.get(symbol, 0.0))
        for symbol in all_symbols
    )
    return gross_change / 2.0
