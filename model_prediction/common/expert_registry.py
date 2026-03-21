"""Registry and path helpers for model experts."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True, slots=True)
class ExpertEntry:
    name: str
    train_script: Path
    predict_script: Path
    description: str


def _script_path(*parts: str) -> Path:
    return PROJECT_ROOT.joinpath(*parts)


EXPERT_REGISTRY: dict[str, ExpertEntry] = {
    "lightgbm": ExpertEntry(
        name="lightgbm",
        train_script=_script_path("model_prediction", "lightgbm", "scripts", "train_lightgbm.py"),
        predict_script=_script_path("model_prediction", "lightgbm", "scripts", "predict_lightgbm.py"),
        description="Gradient boosting tree baseline for tabular stock features.",
    ),
    "xgboost": ExpertEntry(
        name="xgboost",
        train_script=_script_path("model_prediction", "xgboost", "scripts", "train_xgboost.py"),
        predict_script=_script_path("model_prediction", "xgboost", "scripts", "predict_xgboost.py"),
        description="XGBoost expert sharing the same feature and prediction contract.",
    ),
    "catboost": ExpertEntry(
        name="catboost",
        train_script=_script_path("model_prediction", "catboost", "scripts", "train_catboost.py"),
        predict_script=_script_path("model_prediction", "catboost", "scripts", "predict_catboost.py"),
        description="CatBoost expert for tabular stock features with category-friendly boosting.",
    ),
    "lstm": ExpertEntry(
        name="lstm",
        train_script=_script_path("model_prediction", "lstm", "scripts", "train_lstm.py"),
        predict_script=_script_path("model_prediction", "lstm", "scripts", "predict_lstm.py"),
        description="Sequence-model expert based on an LSTM stock forecaster.",
    ),
    "transformer": ExpertEntry(
        name="transformer",
        train_script=_script_path("model_prediction", "transformer", "scripts", "train_transformer.py"),
        predict_script=_script_path("model_prediction", "transformer", "scripts", "predict_transformer.py"),
        description="Sequence-model expert based on a lightweight stock transformer.",
    ),
    "ensemble": ExpertEntry(
        name="ensemble",
        train_script=_script_path("model_prediction", "ensemble", "scripts", "train_ensemble.py"),
        predict_script=_script_path("model_prediction", "ensemble", "scripts", "predict_ensemble.py"),
        description="Ensemble combiner that aggregates outputs from multiple experts.",
    ),
}


def available_experts() -> list[str]:
    return sorted(EXPERT_REGISTRY)


def get_expert(model_name: str) -> ExpertEntry:
    key = str(model_name).strip().lower()
    if key not in EXPERT_REGISTRY:
        supported = ", ".join(available_experts())
        raise KeyError(f"Unsupported model expert: {model_name}. Available: {supported}")
    return EXPERT_REGISTRY[key]


def resolve_script(model_name: str, action: str) -> Path:
    expert = get_expert(model_name)
    normalized = str(action).strip().lower()
    if normalized == "train":
        return expert.train_script
    if normalized == "predict":
        return expert.predict_script
    raise KeyError(f"Unsupported expert action: {action}. Use 'train' or 'predict'.")
