#!/usr/bin/env python3
"""Combine multiple expert prediction files into one ensemble signal file."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

from model_prediction.ensemble.shared import (  # noqa: E402
    SUPPORTED_METHODS,
    combine_predictions,
    default_manifest_path,
    load_expert_frames,
    load_manifest,
    output_dir_for,
    parse_weights,
    save_manifest,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Combine multiple expert prediction files into an ensemble signal."
    )
    parser.add_argument("input_csv", help="Primary prediction CSV produced by one expert.")
    parser.add_argument(
        "--prediction-csv",
        action="append",
        default=[],
        help="Additional expert prediction CSVs to combine.",
    )
    parser.add_argument(
        "--method",
        choices=SUPPORTED_METHODS,
        default="",
        help="Ensemble method used to combine expert scores.",
    )
    parser.add_argument(
        "--weights",
        action="append",
        default=[],
        help="Optional expert weights in the same order as the loaded experts.",
    )
    parser.add_argument(
        "--min-experts",
        type=int,
        default=1,
        help="Minimum number of expert predictions required per row.",
    )
    parser.add_argument(
        "--model-name",
        default="ensemble",
        help="Logical model name used for artifact paths and downstream reporting.",
    )
    parser.add_argument(
        "--output-dir",
        default="",
        help="Directory used to store ensemble outputs.",
    )
    parser.add_argument(
        "--manifest",
        default="",
        help="Optional manifest file to reuse method, weights, and source CSVs.",
    )
    return parser.parse_args()


def dedupe_paths(paths: list[str]) -> list[str]:
    resolved: list[str] = []
    seen: set[str] = set()
    for raw_path in paths:
        path = str(Path(raw_path))
        if path in seen:
            continue
        seen.add(path)
        resolved.append(path)
    return resolved


def main() -> int:
    args = parse_args()
    output_dir = output_dir_for(PROJECT_ROOT, args)
    output_dir.mkdir(parents=True, exist_ok=True)

    manifest_payload: dict[str, object] = {}
    manifest_path = Path(args.manifest) if args.manifest else default_manifest_path(output_dir)
    if manifest_path.exists():
        try:
            manifest_payload = load_manifest(manifest_path)
        except Exception as exc:
            print(f"[WARN] Failed to load manifest {manifest_path}: {exc}")

    prediction_csvs = [args.input_csv, *args.prediction_csv]
    if len(prediction_csvs) == 1 and manifest_payload.get("prediction_csvs"):
        prediction_csvs = [str(item) for item in manifest_payload["prediction_csvs"]]
    prediction_csvs = dedupe_paths(prediction_csvs)

    method = str(args.method or manifest_payload.get("method") or "rank_average")
    if method not in SUPPORTED_METHODS:
        print(f"[ERROR] Unsupported method: {method}")
        return 1

    try:
        merged_df, metadata = load_expert_frames(prediction_csvs, min_experts=args.min_experts)
    except Exception as exc:
        print(f"[ERROR] Failed to load expert predictions: {exc}")
        return 1

    expert_names = [item["model_name"] for item in metadata]
    if args.weights:
        try:
            weights = parse_weights(args.weights, expert_names)
        except Exception as exc:
            print(f"[ERROR] Invalid --weights: {exc}")
            return 1
    elif isinstance(manifest_payload.get("weights"), dict) and manifest_payload["weights"]:
        weights = {
            name: float(manifest_payload["weights"].get(name, 1.0))
            for name in expert_names
        }
    else:
        weights = {name: 1.0 for name in expert_names}

    try:
        combined_df, summary = combine_predictions(merged_df, method=method, weights=weights)
    except Exception as exc:
        print(f"[ERROR] Failed to combine predictions: {exc}")
        return 1

    prepared_path = output_dir / "prepared_dataset.csv"
    combined_path = output_dir / "test_predictions.csv"
    summary_path = output_dir / "predict_summary.json"
    manifest_out = default_manifest_path(output_dir)

    merged_save = merged_df.copy()
    merged_save["date"] = pd.to_datetime(merged_save["date"]).dt.strftime("%Y-%m-%d")
    merged_save.to_csv(prepared_path, index=False, encoding="utf-8")

    combined_save = combined_df.copy()
    combined_save["date"] = pd.to_datetime(combined_save["date"]).dt.strftime("%Y-%m-%d")
    combined_save.to_csv(combined_path, index=False, encoding="utf-8")

    summary.update(
        {
            "model_name": args.model_name,
            "prediction_csvs": prediction_csvs,
            "source_metadata": metadata,
        }
    )
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    manifest_payload = {
        "model_name": args.model_name,
        "method": method,
        "weights": weights,
        "prediction_csvs": prediction_csvs,
        "min_experts": args.min_experts,
        "summary": summary,
        "source_metadata": metadata,
    }
    save_manifest(manifest_out, manifest_payload)

    print(f"[OK] Prepared dataset: {prepared_path}")
    print(f"[OK] Predictions file: {combined_path}")
    print(f"[OK] Manifest: {manifest_out}")
    print(f"[OK] Predict summary: {summary_path}")
    print(f"[INFO] Expert count: {len(expert_names)}")
    print(f"[INFO] Rows: {summary['row_count']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
