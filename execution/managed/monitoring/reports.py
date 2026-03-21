from __future__ import annotations

from dataclasses import asdict, dataclass, field, is_dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Mapping
from uuid import uuid4

from execution.managed.state.models import RunManifestRecord


PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_RUNTIME_ROOT = PROJECT_ROOT / "execution" / "runtime"


@dataclass(slots=True, frozen=True)
class PaperRunFailure:
    stage: str
    reason: str
    details: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {"stage": self.stage, "reason": self.reason, "details": dict(self.details)}


@dataclass(slots=True, frozen=True)
class PaperRunReport:
    run_id: str
    session_date: date
    status: str
    dry_run: bool
    stage: str
    counts: Mapping[str, int] = field(default_factory=dict)
    failures: tuple[PaperRunFailure, ...] = ()
    meta: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "session_date": self.session_date.isoformat(),
            "status": self.status,
            "dry_run": self.dry_run,
            "stage": self.stage,
            "counts": dict(self.counts),
            "failures": [failure.to_dict() for failure in self.failures],
            "meta": dict(self.meta),
        }


@dataclass(slots=True, frozen=True)
class PaperRunManifest:
    run_id: str
    session_date: date
    strategy_name: str
    model_name: str
    dry_run: bool
    client_order_id_prefix: str
    generated_at_utc: datetime
    data_snapshot: Mapping[str, Any] = field(default_factory=dict)
    risk_policy: Mapping[str, Any] = field(default_factory=dict)
    execution_policy: Mapping[str, Any] = field(default_factory=dict)
    meta: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "session_date": self.session_date.isoformat(),
            "strategy_name": self.strategy_name,
            "model_name": self.model_name,
            "dry_run": self.dry_run,
            "client_order_id_prefix": self.client_order_id_prefix,
            "generated_at_utc": self.generated_at_utc.astimezone(timezone.utc).isoformat(),
            "data_snapshot": dict(self.data_snapshot),
            "risk_policy": dict(self.risk_policy),
            "execution_policy": dict(self.execution_policy),
            "meta": dict(self.meta),
        }

    def to_record(self) -> RunManifestRecord:
        return RunManifestRecord(
            run_id=self.run_id,
            session_date=self.session_date,
            strategy_name=self.strategy_name,
            model_name=self.model_name,
            generated_at_utc=self.generated_at_utc,
            client_order_id_prefix=self.client_order_id_prefix,
            dry_run=self.dry_run,
            data_snapshot=dict(self.data_snapshot),
            risk_policy=dict(self.risk_policy),
            execution_policy=dict(self.execution_policy),
            meta=dict(self.meta),
        )


@dataclass(slots=True, frozen=True)
class PaperArtifactLink:
    artifact_dir: Path | None
    source: str
    exists: bool
    files: Mapping[str, str] = field(default_factory=dict)
    candidates: tuple[str, ...] = ()
    notes: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "artifact_dir": str(self.artifact_dir) if self.artifact_dir is not None else None,
            "source": self.source,
            "exists": self.exists,
            "files": dict(self.files),
            "candidates": list(self.candidates),
            "notes": list(self.notes),
        }


def build_paper_run_report(
    *,
    session_date: date,
    dry_run: bool,
    stage: str,
    counts: Mapping[str, int],
    failures: tuple[PaperRunFailure, ...] = (),
    meta: Mapping[str, Any] | None = None,
    run_id: str | None = None,
    manifest: PaperRunManifest | Mapping[str, Any] | None = None,
    status: str | None = None,
) -> PaperRunReport:
    resolved_run_id = run_id or uuid4().hex
    resolved_status = status or ("failed" if failures else "success")
    report_meta = dict(meta or {})
    if manifest is not None:
        report_meta["run_manifest"] = manifest.to_dict() if isinstance(manifest, PaperRunManifest) else dict(manifest)
    return PaperRunReport(
        run_id=resolved_run_id,
        session_date=session_date,
        status=resolved_status,
        dry_run=dry_run,
        stage=stage,
        counts=dict(counts),
        failures=failures,
        meta=report_meta,
    )


def build_paper_run_manifest(
    *,
    run_id: str,
    session_date: date,
    strategy_name: str,
    model_name: str,
    dry_run: bool,
    client_order_id_prefix: str = "smk",
    generated_at_utc: datetime | None = None,
    data_snapshot: Mapping[str, Any] | None = None,
    risk_policy: Mapping[str, Any] | None = None,
    execution_policy: Mapping[str, Any] | None = None,
    meta: Mapping[str, Any] | None = None,
) -> PaperRunManifest:
    return PaperRunManifest(
        run_id=run_id,
        session_date=session_date,
        strategy_name=strategy_name,
        model_name=model_name,
        dry_run=dry_run,
        client_order_id_prefix=client_order_id_prefix,
        generated_at_utc=generated_at_utc or datetime.now(timezone.utc),
        data_snapshot=dict(data_snapshot or {}),
        risk_policy=dict(risk_policy or {}),
        execution_policy=dict(execution_policy or {}),
        meta=dict(meta or {}),
    )


def build_paper_artifact_link(
    *,
    artifact_dir: str | Path | None = None,
    artifact_root: str | Path = DEFAULT_RUNTIME_ROOT,
    manifest: PaperRunManifest | Mapping[str, Any] | None = None,
    strategy_id: str | None = None,
    session_date: date | None = None,
    model_name: str | None = None,
) -> PaperArtifactLink:
    manifest_payload = _manifest_payload(manifest)
    resolved, source, candidates, notes = _resolve_artifact_dir(
        explicit_artifact_dir=artifact_dir,
        artifact_root=artifact_root,
        manifest_payload=manifest_payload,
        strategy_id=strategy_id,
        session_date=session_date,
        model_name=model_name,
    )
    files = {}
    if resolved is not None:
        files = {
            "execution_plan": str(resolved / "execution_plan.json"),
            "target_positions": str(resolved / "target_positions.csv"),
            "order_intents": str(resolved / "order_intents.csv"),
            "run_summary": str(resolved / "run_summary.json"),
        }
    return PaperArtifactLink(
        artifact_dir=resolved,
        source=source,
        exists=resolved.exists() if resolved is not None else False,
        files=files,
        candidates=candidates,
        notes=notes,
    )


def _manifest_payload(manifest: PaperRunManifest | Mapping[str, Any] | None) -> dict[str, Any]:
    if manifest is None:
        return {}
    if isinstance(manifest, PaperRunManifest):
        return manifest.to_dict()
    return dict(manifest)


def _resolve_artifact_dir(
    *,
    explicit_artifact_dir: str | Path | None,
    artifact_root: str | Path,
    manifest_payload: Mapping[str, Any],
    strategy_id: str | None,
    session_date: date | None,
    model_name: str | None,
) -> tuple[Path | None, str, tuple[str, ...], tuple[str, ...]]:
    if explicit_artifact_dir is not None:
        resolved = Path(explicit_artifact_dir)
        return resolved, "explicit", (str(resolved),), ()

    meta = dict(manifest_payload.get("meta") or {})
    manifest_candidate = (
        meta.get("artifact_dir")
        or meta.get("artifacts_dir")
        or meta.get("backtest_artifact_dir")
        or meta.get("research_artifact_dir")
        or meta.get("latest_runtime_dir")
        or meta.get("run_dir")
    )
    if manifest_candidate is not None:
        resolved = Path(str(manifest_candidate))
        return resolved, "manifest_meta", (str(resolved),), ()

    strategy_name = strategy_id or str(meta.get("strategy_id") or meta.get("strategy_name") or "").strip() or None
    root = Path(artifact_root)
    if not root.exists():
        return None, "unresolved", (), ("artifact_root_missing",)

    candidates = _discover_artifact_candidates(root, strategy_name=strategy_name)
    candidate_strings = tuple(str(candidate) for candidate in candidates)
    if not candidates:
        return None, "unresolved", candidate_strings, ("artifact_root_has_no_candidates",)

    requested_date = session_date.isoformat() if session_date is not None else None
    scored_candidates: list[tuple[int, int, Path, tuple[str, ...]]] = []
    for candidate in candidates:
        candidate_text = str(candidate).lower()
        candidate_name = candidate.name.lower()
        notes: list[str] = []
        score = 0

        if strategy_name:
            if strategy_name.lower() in candidate_text or strategy_name.lower() in candidate_name:
                score += 4
                notes.append("matched_strategy_name")
            else:
                notes.append("missing_strategy_name_match")
        if model_name:
            if model_name.lower() in candidate_text or model_name.lower() in candidate_name:
                score += 3
                notes.append("matched_model_name")
            else:
                notes.append("missing_model_name_match")
        if requested_date:
            if requested_date in candidate_text or requested_date in candidate_name:
                score += 2
                notes.append("matched_session_date")
            else:
                notes.append("missing_session_date_match")

        scored_candidates.append((score, int(_artifact_mtime(candidate)), candidate, tuple(notes)))

    scored_candidates.sort(key=lambda item: (item[0], item[1], str(item[2])), reverse=True)
    best_score, _, best_candidate, best_notes = scored_candidates[0]
    if best_score <= 0 and (strategy_name or model_name or requested_date):
        return None, "unresolved", candidate_strings, ("no_direct_match_found",)

    return best_candidate, "discovered", candidate_strings, best_notes


def _discover_artifact_candidates(root: Path, *, strategy_name: str | None = None) -> list[Path]:
    required_files = ("execution_plan.json", "target_positions.csv", "order_intents.csv", "run_summary.json")
    candidates: list[Path] = []
    strategy_roots = [root]
    if strategy_name:
        strategy_root = root / strategy_name
        if strategy_root.exists():
            strategy_roots = [strategy_root]

    for base in strategy_roots:
        for summary_file in base.rglob("run_summary.json"):
            parent = summary_file.parent
            if all((parent / file_name).exists() for file_name in required_files):
                candidates.append(parent)
    return sorted(set(candidates), key=lambda path: (_artifact_mtime(path), str(path)), reverse=True)


def _artifact_mtime(path: Path) -> float:
    mtimes = []
    for file_name in ("execution_plan.json", "target_positions.csv", "order_intents.csv", "run_summary.json"):
        candidate = path / file_name
        if candidate.exists():
            mtimes.append(candidate.stat().st_mtime)
    return max(mtimes) if mtimes else 0.0

