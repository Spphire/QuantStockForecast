from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True, slots=True)
class ExpertSpec:
    model_name: str
    train_script: str
    predict_script: str
    model_file: str
    train_args: tuple[str, ...]
    predict_args: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ExpertArtifact:
    spec: ExpertSpec
    train_dir: Path
    predict_dir: Path
    model_path: Path
    metrics_path: Path
    train_predictions_path: Path
    predict_predictions_path: Path


EXPERT_SPECS = (
    ExpertSpec(
        model_name="lightgbm",
        train_script="model_prediction/lightgbm/scripts/train_lightgbm.py",
        predict_script="model_prediction/lightgbm/scripts/predict_lightgbm.py",
        model_file="model.txt",
        train_args=("--mode", "regression", "--horizon", "5", "--num-boost-round", "12"),
    ),
    ExpertSpec(
        model_name="xgboost",
        train_script="model_prediction/xgboost/scripts/train_xgboost.py",
        predict_script="model_prediction/xgboost/scripts/predict_xgboost.py",
        model_file="model.json",
        train_args=("--mode", "regression", "--horizon", "5", "--num-boost-round", "12"),
    ),
    ExpertSpec(
        model_name="catboost",
        train_script="model_prediction/catboost/scripts/train_catboost.py",
        predict_script="model_prediction/catboost/scripts/predict_catboost.py",
        model_file="model.cbm",
        train_args=("--mode", "regression", "--horizon", "5", "--num-boost-round", "12"),
    ),
    ExpertSpec(
        model_name="lstm",
        train_script="model_prediction/lstm/scripts/train_lstm.py",
        predict_script="model_prediction/lstm/scripts/predict_lstm.py",
        model_file="model.pt",
        train_args=(
            "--mode",
            "regression",
            "--horizon",
            "5",
            "--seq-len",
            "20",
            "--hidden-size",
            "16",
            "--num-layers",
            "1",
            "--dropout",
            "0.0",
            "--batch-size",
            "32",
            "--epochs",
            "2",
            "--patience",
            "1",
            "--device",
            "cpu",
        ),
        predict_args=("--device", "cpu"),
    ),
    ExpertSpec(
        model_name="transformer",
        train_script="model_prediction/transformer/scripts/train_transformer.py",
        predict_script="model_prediction/transformer/scripts/predict_transformer.py",
        model_file="model.pt",
        train_args=(
            "--mode",
            "regression",
            "--horizon",
            "5",
            "--lookback",
            "20",
            "--hidden-dim",
            "16",
            "--num-layers",
            "1",
            "--num-heads",
            "2",
            "--dropout",
            "0.0",
            "--batch-size",
            "32",
            "--max-epochs",
            "2",
            "--patience",
            "1",
            "--device",
            "cpu",
        ),
    ),
)


def _run_command(args: list[str]) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        [sys.executable, *args],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise AssertionError(
            f"Command failed: {' '.join(args)}\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )
    return result


@pytest.fixture(scope="session")
def synthetic_universe_csv(tmp_path_factory: pytest.TempPathFactory) -> Path:
    output_dir = tmp_path_factory.mktemp("synthetic_market_data")
    output_path = output_dir / "synthetic_universe.csv"

    dates = pd.bdate_range("2024-01-02", periods=180)
    symbols = ("AAA", "BBB", "CCC", "DDD", "EEE", "FFF")
    rng = np.random.default_rng(42)
    rows: list[dict[str, object]] = []

    for index, symbol in enumerate(symbols):
        price = 40.0 + index * 11.0
        drift = 0.0008 + index * 0.00015
        for date_index, current_date in enumerate(dates):
            noise = rng.normal(0.0, 0.012)
            seasonal = 0.01 * np.sin((date_index + index * 3) / 14.0)
            daily_return = drift + seasonal + noise
            open_price = price * (1.0 + rng.normal(0.0, 0.003))
            close_price = max(5.0, price * (1.0 + daily_return))
            high_price = max(open_price, close_price) * (1.0 + abs(rng.normal(0.0, 0.006)))
            low_price = min(open_price, close_price) * max(0.7, 1.0 - abs(rng.normal(0.0, 0.006)))
            volume = int(1_000_000 + index * 120_000 + rng.integers(0, 400_000))
            amount = close_price * volume
            turnover = 0.01 + index * 0.001 + abs(rng.normal(0.0, 0.002))
            rows.append(
                {
                    "date": current_date.strftime("%Y-%m-%d"),
                    "symbol": symbol,
                    "open": round(open_price, 4),
                    "high": round(high_price, 4),
                    "low": round(low_price, 4),
                    "close": round(close_price, 4),
                    "volume": volume,
                    "amount": round(amount, 2),
                    "turnover": round(turnover, 6),
                }
            )
            price = close_price

    pd.DataFrame(rows).to_csv(output_path, index=False, encoding="utf-8")
    return output_path


@pytest.fixture(scope="session")
def trained_experts(
    synthetic_universe_csv: Path,
    tmp_path_factory: pytest.TempPathFactory,
) -> dict[str, ExpertArtifact]:
    output_root = tmp_path_factory.mktemp("expert_training_runs")
    artifacts: dict[str, ExpertArtifact] = {}

    for spec in EXPERT_SPECS:
        train_dir = output_root / spec.model_name / "train"
        predict_dir = output_root / spec.model_name / "predict"
        _run_command(
            [
                spec.train_script,
                str(synthetic_universe_csv),
                "--output-dir",
                str(train_dir),
                *spec.train_args,
            ]
        )

        model_path = train_dir / spec.model_file
        metrics_path = train_dir / "metrics.json"
        train_predictions_path = train_dir / "test_predictions.csv"
        assert model_path.exists()
        assert metrics_path.exists()
        assert train_predictions_path.exists()

        _run_command(
            [
                spec.predict_script,
                str(synthetic_universe_csv),
                "--model-path",
                str(model_path),
                "--reference-metrics",
                str(metrics_path),
                "--output-dir",
                str(predict_dir),
                *spec.predict_args,
            ]
        )

        predict_predictions_path = predict_dir / "test_predictions.csv"
        assert predict_predictions_path.exists()
        artifacts[spec.model_name] = ExpertArtifact(
            spec=spec,
            train_dir=train_dir,
            predict_dir=predict_dir,
            model_path=model_path,
            metrics_path=metrics_path,
            train_predictions_path=train_predictions_path,
            predict_predictions_path=predict_predictions_path,
        )

    return artifacts


@pytest.fixture(scope="session")
def trained_ensemble(
    trained_experts: dict[str, ExpertArtifact],
    tmp_path_factory: pytest.TempPathFactory,
) -> Path:
    output_dir = tmp_path_factory.mktemp("ensemble_training_run")
    predictions = [
        str(artifact.predict_predictions_path)
        for artifact in trained_experts.values()
    ]
    _run_command(
        [
            "model_prediction/ensemble/scripts/train_ensemble.py",
            predictions[0],
            "--prediction-csv",
            predictions[1],
            "--prediction-csv",
            predictions[2],
            "--prediction-csv",
            predictions[3],
            "--prediction-csv",
            predictions[4],
            "--method",
            "mean_score",
            "--min-experts",
            "5",
            "--model-name",
            "synthetic_multi_expert",
            "--output-dir",
            str(output_dir),
        ]
    )
    return output_dir


@pytest.fixture(scope="session")
def synthetic_risk_output(
    trained_ensemble: Path,
    tmp_path_factory: pytest.TempPathFactory,
) -> Path:
    output_dir = tmp_path_factory.mktemp("synthetic_risk_run")
    _run_command(
        [
            "risk_management/white_box/scripts/run_white_box_risk.py",
            str(trained_ensemble / "test_predictions.csv"),
            "--output-dir",
            str(output_dir),
            "--top-k",
            "3",
            "--rebalance-step",
            "5",
            "--min-score",
            "0",
            "--max-position-weight",
            "0.5",
            "--transaction-cost-bps",
            "10",
        ]
    )
    return output_dir


@pytest.mark.parametrize("model_name", [spec.model_name for spec in EXPERT_SPECS])
def test_each_expert_trains_and_predicts(
    trained_experts: dict[str, ExpertArtifact],
    model_name: str,
) -> None:
    artifact = trained_experts[model_name]
    metrics = json.loads(artifact.metrics_path.read_text(encoding="utf-8"))
    train_predictions = pd.read_csv(artifact.train_predictions_path)
    predict_predictions = pd.read_csv(artifact.predict_predictions_path)

    assert metrics["mode"] == "regression"
    assert artifact.model_path.exists()
    assert len(train_predictions) > 0
    assert len(predict_predictions) > 0
    assert {"date", "symbol", "close"}.issubset(train_predictions.columns)
    assert {"date", "symbol", "close"}.issubset(predict_predictions.columns)


def test_ensemble_training_combines_all_experts(
    trained_ensemble: Path,
) -> None:
    predictions_path = trained_ensemble / "test_predictions.csv"
    manifest_path = trained_ensemble / "ensemble_manifest.json"
    summary_path = trained_ensemble / "predict_summary.json"

    predictions = pd.read_csv(predictions_path)
    summary = json.loads(summary_path.read_text(encoding="utf-8"))

    assert predictions_path.exists()
    assert manifest_path.exists()
    assert summary_path.exists()
    assert len(predictions) > 0
    assert {"date", "symbol", "pred_score", "ensemble_confidence"}.issubset(predictions.columns)
    assert summary["model_name"] == "synthetic_multi_expert"
    assert summary["method"] == "mean_score"


def test_white_box_risk_consumes_ensemble_predictions(
    synthetic_risk_output: Path,
) -> None:
    positions_path = synthetic_risk_output / "risk_positions.csv"
    actions_path = synthetic_risk_output / "risk_actions.csv"
    summary_path = synthetic_risk_output / "risk_summary.json"

    positions = pd.read_csv(positions_path)
    actions = pd.read_csv(actions_path)
    summary = json.loads(summary_path.read_text(encoding="utf-8"))

    assert positions_path.exists()
    assert actions_path.exists()
    assert summary_path.exists()
    assert len(positions) > 0
    assert len(actions) > 0
    assert {"rebalance_date", "symbol", "target_weight"}.issubset(positions.columns)
    assert "total_return" in summary
