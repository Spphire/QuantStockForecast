from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from execution.managed.briefing.chart_assets import generate_brief_chart_assets
from execution.managed.briefing.html_exporter import export_html_to_png
from execution.managed.briefing.html_templates import A4_HEIGHT_PX, A4_WIDTH_PX, render_brief_html


def render_operation_brief_html_page(
    *,
    brief: Mapping[str, Any],
    run_dir: Path,
    html_path: Path,
    dashboard_path: Path,
) -> dict[str, Any]:
    charts_dir = run_dir / "charts"
    chart_payload = generate_brief_chart_assets(brief=brief, output_dir=charts_dir)
    chart_payload_rel = _relativize_chart_paths(chart_payload=chart_payload, base_dir=run_dir)
    html_content = render_brief_html(brief=brief, chart_payload=chart_payload_rel)
    html_path.write_text(html_content, encoding="utf-8")
    export_html_to_png(
        html_path=html_path,
        output_path=dashboard_path,
        width=A4_WIDTH_PX,
        height=A4_HEIGHT_PX,
        device_scale_factor=2.0,
    )
    manifest_path = run_dir / "charts_manifest.json"
    manifest_path.write_text(json.dumps(chart_payload_rel, ensure_ascii=False, indent=2), encoding="utf-8")
    return {
        "renderer": "html_playwright",
        "charts_dir": str(charts_dir),
        "charts_manifest": str(manifest_path),
        "page_size": {"width": A4_WIDTH_PX, "height": A4_HEIGHT_PX},
    }


def _relativize_chart_paths(*, chart_payload: Mapping[str, Any], base_dir: Path) -> dict[str, Any]:
    base_abs = base_dir.resolve()
    result = {
        "phase": str(chart_payload.get("phase") or ""),
        "chart_dir": str(chart_payload.get("chart_dir") or ""),
        "strategies": [],
    }
    for raw_entry in list(chart_payload.get("strategies") or []):
        if not isinstance(raw_entry, Mapping):
            continue
        entry = dict(raw_entry)
        charts = {}
        for name, raw_path in dict(entry.get("charts") or {}).items():
            path_value = str(raw_path or "").strip()
            if not path_value:
                charts[name] = ""
                continue
            path_obj = Path(path_value)
            try:
                rel = path_obj.resolve().relative_to(base_abs)
                charts[name] = str(rel).replace("\\", "/")
            except Exception:
                try:
                    charts[name] = path_obj.resolve().as_uri()
                except Exception:
                    charts[name] = path_value.replace("\\", "/")
        entry["charts"] = charts
        result["strategies"].append(entry)
    return result


__all__ = ["render_operation_brief_html_page"]
