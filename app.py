"""
Streamlit UI for TCR & RQD analysis using compute_tcr_rqd from colab.py.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import streamlit as st

from tcr_utils import (
    call_compute_tcr_rqd,
    find_debug_images,
    normalize_runs,
    runs_to_ui_rows,
)


def main() -> None:
    st.set_page_config(page_title="TCR & RQD Analyzer", layout="wide")

    with st.container():
        st.title("TCR & RQD Analyzer")
        st.caption(
            "Upload a borehole core box image to compute Total Core Recovery and Rock Quality Designation."
        )

    with st.container():
        uploaded = st.file_uploader(
            "Core box image",
            type=["jpg", "jpeg", "png", "webp", "bmp", "tif", "tiff"],
        )

        col_img, col_action = st.columns([1.1, 1])
        with col_img:
            st.subheader("Uploaded image")
            if uploaded is not None:
                st.image(uploaded, use_container_width=True)
            else:
                st.info("Choose an image file to begin.")

        with col_action:
            st.subheader("Analysis")
            analyze = st.button("Analyze", type="primary", disabled=uploaded is None)

    if not analyze or uploaded is None:
        return

    suffix = Path(uploaded.name).suffix.lower() or ".jpg"
    if suffix not in {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff"}:
        suffix = ".jpg"

    tmp_path: str | None = None
    try:
        with st.spinner("Analyzing image…"):
            fd, tmp_path = tempfile.mkstemp(suffix=suffix, prefix="tcr_rqd_")
            os.close(fd)
            with open(tmp_path, "wb") as f:
                f.write(uploaded.getbuffer())

            results = call_compute_tcr_rqd(tmp_path, debug=True)

        runs = normalize_runs(results)
        img_dir = Path(tmp_path).parent

        with st.container():
            st.divider()
            st.subheader("Results")

            if not runs:
                st.warning(
                    "No per-run results could be parsed. Expected a list of dicts with "
                    "keys like run, TCR, RQD, n_pieces (as returned by colab.compute_tcr_rqd)."
                )
                st.json(results if isinstance(results, (dict, list)) else {"raw": str(results)})
            else:
                table_rows = []
                for row in runs_to_ui_rows(runs):
                    table_rows.append(
                        {
                            "Run": row["run"],
                            "TCR (%)": row["tcr_pct"],
                            "RQD (%)": row["rqd_pct"],
                            "Pieces": row["pieces"],
                        }
                    )

                st.dataframe(table_rows, use_container_width=True, hide_index=True)

        debug_paths = find_debug_images([img_dir, Path.cwd()])
        if debug_paths:
            with st.container():
                st.divider()
                st.subheader("Debug Visualization")
                n = len(debug_paths)
                dbg_cols = st.columns(min(3, max(1, n)))
                for i, p in enumerate(debug_paths):
                    with dbg_cols[i % len(dbg_cols)]:
                        st.caption(p.name)
                        st.image(str(p), use_container_width=True)

    except Exception as e:
        st.error(f"Analysis failed: {e}")
    finally:
        if tmp_path and os.path.isfile(tmp_path):
            try:
                os.unlink(tmp_path)
            except OSError:
                pass


if __name__ == "__main__":
    main()
