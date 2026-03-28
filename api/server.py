"""
FastAPI server for the React UI. Run from project root:
  uvicorn api.server:app --reload --host 127.0.0.1 --port 8000
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

# Project root (parent of api/)
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware

from tcr_utils import (
    call_compute_tcr_rqd,
    debug_images_to_payload,
    find_debug_images,
    normalize_runs,
    runs_to_ui_rows,
)

app = FastAPI(title="TCR & RQD API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=os.environ.get("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(
        ","
    ),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/analyze")
async def analyze(file: UploadFile = File(...)) -> dict:
    suffix = Path(file.filename or "upload.jpg").suffix.lower() or ".jpg"
    if suffix not in {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff"}:
        suffix = ".jpg"

    tmp_path: str | None = None
    try:
        fd, tmp_path = tempfile.mkstemp(suffix=suffix, prefix="tcr_rqd_")
        os.close(fd)
        content = await file.read()
        with open(tmp_path, "wb") as f:
            f.write(content)

        raw = call_compute_tcr_rqd(tmp_path, debug=True)
        runs = normalize_runs(raw)
        img_dir = Path(tmp_path).parent

        debug_paths = find_debug_images([img_dir, ROOT])
        debug_payload = debug_images_to_payload(debug_paths)

        if not runs:
            return {
                "ok": True,
                "runs": [],
                "raw": raw if isinstance(raw, (dict, list)) else {"repr": str(raw)},
                "debug_images": debug_payload,
                "warning": "Could not parse per-run results; see raw payload.",
            }

        return {
            "ok": True,
            "runs": runs_to_ui_rows(runs),
            "debug_images": debug_payload,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
    finally:
        if tmp_path and os.path.isfile(tmp_path):
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
