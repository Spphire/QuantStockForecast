from __future__ import annotations

from pathlib import Path


def export_html_to_png(
    *,
    html_path: Path,
    output_path: Path,
    width: int,
    height: int,
    device_scale_factor: float = 2.0,
) -> None:
    html_abs = html_path.resolve()
    if not html_abs.exists():
        raise FileNotFoundError(f"HTML file not found: {html_abs}")

    from playwright.sync_api import sync_playwright

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={"width": int(width), "height": int(height)},
            device_scale_factor=float(device_scale_factor),
        )
        page = context.new_page()
        page.goto(html_abs.as_uri(), wait_until="networkidle")
        page.wait_for_timeout(180)
        page.screenshot(path=str(output_path), full_page=False)
        context.close()
        browser.close()


__all__ = ["export_html_to_png"]
