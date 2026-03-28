"""Shared helpers for Streamlit app and REST API (normalize runs, debug paths)."""

from __future__ import annotations

import base64
import inspect
import mimetypes
from pathlib import Path
from typing import Any

from colab import compute_tcr_rqd


def _get_num(obj: dict[str, Any], *keys: str, default: int = 0) -> int:
    for k in keys:
        if k in obj and obj[k] is not None:
            try:
                return int(obj[k])
            except (TypeError, ValueError):
                pass
    return default


def _get_pct(obj: dict[str, Any], *keys: str) -> float | None:
    for k in keys:
        if k in obj and obj[k] is not None:
            try:
                return float(obj[k])
            except (TypeError, ValueError):
                pass
    return None


def normalize_runs(result: Any) -> list[dict[str, Any]]:
    """
    Normalize compute_tcr_rqd output to rows with:
    run_index, tcr, rqd, num_pieces.
    """
    if result is None:
        return []

    if isinstance(result, list):
        rows: list[dict[str, Any]] = []
        for i, item in enumerate(result):
            if not isinstance(item, dict):
                continue
            rows.append(
                {
                    "run_index": int(
                        item.get("run", item.get("run_index", item.get("index", i)))
                    ),
                    "tcr": _get_pct(item, "TCR", "tcr", "tcr_pct"),
                    "rqd": _get_pct(item, "RQD", "rqd", "rqd_pct"),
                    "num_pieces": _get_num(item, "n_pieces", "num_pieces", "pieces", "piece_count"),
                }
            )
        return rows

    if isinstance(result, dict):
        if "runs" in result and isinstance(result["runs"], list):
            return normalize_runs(result["runs"])
        tcr = _get_pct(result, "TCR", "tcr", "tcr_pct")
        rqd = _get_pct(result, "RQD", "rqd", "rqd_pct")
        n = _get_num(result, "n_pieces", "num_pieces", "pieces", "piece_count")
        if tcr is not None or rqd is not None or n:
            return [
                {
                    "run_index": int(result.get("run", result.get("run_index", 0))),
                    "tcr": tcr,
                    "rqd": rqd,
                    "num_pieces": n,
                }
            ]

    return []


def call_compute_tcr_rqd(image_path: str, debug: bool = True) -> Any:
    sig = inspect.signature(compute_tcr_rqd)
    if "debug" in sig.parameters:
        return compute_tcr_rqd(image_path, debug=debug)
    return compute_tcr_rqd(image_path)


def find_debug_images(search_dirs: list[Path]) -> list[Path]:
    paths: list[Path] = []
    for d in search_dirs:
        if not d.is_dir():
            continue
        for pattern in ("debug_*.jpg", "debug_*.jpeg", "debug_*.png"):
            paths.extend(sorted(d.glob(pattern)))
    seen: set[str] = set()
    unique: list[Path] = []
    for p in paths:
        key = str(p.resolve())
        if key not in seen:
            seen.add(key)
            unique.append(p)
    return unique


def runs_to_ui_rows(runs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """1-based run numbers when colab uses 0-based indices."""
    if not runs:
        return []
    min_run = min(x["run_index"] for x in runs)
    table_rows: list[dict[str, Any]] = []
    for r in runs:
        ri = r["run_index"]
        run_no = ri + 1 if min_run == 0 else ri
        table_rows.append(
            {
                "run": run_no,
                "tcr_pct": None if r.get("tcr") is None else round(float(r["tcr"]), 2),
                "rqd_pct": None if r.get("rqd") is None else round(float(r["rqd"]), 2),
                "pieces": r.get("num_pieces", 0),
            }
        )
    return table_rows


def debug_images_to_payload(paths: list[Path]) -> list[dict[str, str]]:
    """Return {filename, mime, data_b64} for JSON responses."""
    out: list[dict[str, str]] = []
    for p in paths:
        mime, _ = mimetypes.guess_type(p.name)
        if not mime:
            mime = "application/octet-stream"
        raw = p.read_bytes()
        out.append(
            {
                "filename": p.name,
                "mime": mime,
                "data_b64": base64.b64encode(raw).decode("ascii"),
            }
        )
    return out
