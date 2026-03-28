# -*- coding: utf-8 -*-
"""TCR / RQD pipeline — v3 with debug mode.

The original Colab export contained invalid Python (!pip magics) and a duplicate
second pipeline; those were removed so this module imports cleanly for Streamlit
and FastAPI. Core detection and `compute_tcr_rqd` logic below is unchanged.
"""

import cv2
import numpy as np
from scipy.signal import find_peaks
import os

# ─────────────────────────────────────────────────────────────────
# CONFIGURATION  ← tune these if results are wrong
# ─────────────────────────────────────────────────────────────────
RUN_LENGTH_CM      = 150      # Each core run = 1.5 m
RQD_MIN_CM         = 10       # Standard geotechnical threshold
RESIZE_W           = 1200     # Wider = better resolution for small pieces
RESIZE_H           = 900

# Tray width calibration
# Option A (auto):   set TRAY_WIDTH_PX = None  → pipeline estimates it
# Option B (manual): set TRAY_WIDTH_PX = <integer>  → use fixed value
#   To find the right value: run with --debug, open debug_Picture1.jpg,
#   measure the pixel distance between the inner left and right tray walls.
TRAY_WIDTH_PX      = None     # e.g. set to 980 after calibrating

# Piece detection filters (in pixels, after resize to RESIZE_W x RESIZE_H)
MIN_PIECE_W        = 25       # ignore tiny fragments
MAX_PIECE_W_RATIO  = 0.50     # ignore anything wider than 50% of image (labels, rows)
MIN_PIECE_H        = 12
MAX_PIECE_H        = 160

# Run detection
MIN_RUNS           = 2
MAX_RUNS           = 10
# ─────────────────────────────────────────────────────────────────


def estimate_tray_width(img, debug=False):
    """
    Estimate tray interior width in pixels.
    Strategy: look at a horizontal band in the MIDDLE of the image,
    find the dominant left and right vertical edges.
    """
    h, w = img.shape[:2]

    y1, y2 = int(h * 0.30), int(h * 0.70)
    strip  = img[y1:y2, :]

    gray       = cv2.cvtColor(strip, cv2.COLOR_BGR2GRAY)
    sobelx     = cv2.Sobel(gray, cv2.CV_64F, 1, 0, ksize=5)
    col_energy = np.sum(np.abs(sobelx), axis=0)
    smooth     = np.convolve(col_energy, np.ones(15) / 15, mode='same')

    peaks, _ = find_peaks(
        smooth,
        distance=w // 5,
        height=np.max(smooth) * 0.25,
        prominence=np.max(smooth) * 0.10
    )

    if debug:
        print(f"  [calibrate] image width={w}px, detected wall peaks at x={peaks}")

    if len(peaks) >= 2:
        left_wall  = peaks[0]
        right_wall = peaks[-1]
        if (right_wall - left_wall) > w * 0.40:
            tray_w = right_wall - left_wall
            if debug:
                print(f"  [calibrate] tray width estimated: {tray_w}px "
                      f"(left={left_wall}, right={right_wall})")
            return tray_w, left_wall, right_wall

    fallback = int(w * 0.75)
    margin   = (w - fallback) // 2
    if debug:
        print(f"  [calibrate] wall detection failed, using fallback: {fallback}px")
    return fallback, margin, margin + fallback


def detect_runs(edges, img_h, debug=False):
    """
    Detect horizontal run bands using valley-finding on edge projection.
    """
    h_proj = np.sum(edges, axis=1).astype(float)
    smooth = np.convolve(h_proj, np.ones(40) / 40, mode='same')

    inv_smooth = np.max(smooth) - smooth
    valleys, _ = find_peaks(
        inv_smooth,
        distance=img_h // (MAX_RUNS + 2),
        prominence=np.max(inv_smooth) * 0.10
    )

    boundaries = np.sort(np.concatenate([[0], valleys, [img_h]]))
    runs = [
        (int(boundaries[i]), int(boundaries[i + 1]))
        for i in range(len(boundaries) - 1)
        if (boundaries[i + 1] - boundaries[i]) > img_h * 0.04
    ]

    if debug:
        print(f"  [runs] detected {len(runs)} runs")

    if not (MIN_RUNS <= len(runs) <= MAX_RUNS):
        n    = 4
        step = img_h // n
        runs = [(i * step, (i + 1) * step) for i in range(n)]
        if debug:
            print(f"  [runs] fallback: using {n} equal runs")

    return runs


def detect_pieces(img, tray_x_left, tray_x_right):
    """
    Detect core piece bounding boxes restricted to tray interior.
    """
    gray  = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    blur  = cv2.GaussianBlur(gray, (5, 5), 0)
    edges = cv2.Canny(blur, 25, 90)

    mask = np.zeros_like(edges)
    mask[:, tray_x_left:tray_x_right] = 255
    edges = cv2.bitwise_and(edges, mask)

    contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    tray_w    = tray_x_right - tray_x_left
    raw_boxes = []

    for cnt in contours:
        x, y, w, h = cv2.boundingRect(cnt)
        if (MIN_PIECE_W < w < tray_w * MAX_PIECE_W_RATIO and
                MIN_PIECE_H < h < MAX_PIECE_H):
            raw_boxes.append((x, y, w, h))

    filtered = []
    for box in sorted(raw_boxes, key=lambda b: b[2] * b[3], reverse=True):
        x, y, w, h = box
        if not any(
            x >= x2 and y >= y2 and
            (x + w) <= (x2 + w2) and (y + h) <= (y2 + h2)
            for (x2, y2, w2, h2) in filtered
        ):
            filtered.append(box)

    return filtered, edges


def split_piece(gray_crop, pixels_per_cm):
    """Split a piece at internal fractures. Returns list of lengths in cm."""
    if gray_crop.size == 0:
        return []
    h, w      = gray_crop.shape
    vert_proj = np.sum(gray_crop, axis=0).astype(float)
    smooth    = np.convolve(vert_proj, np.ones(8) / 8, mode='same')
    threshold = np.median(smooth) * 0.60
    gaps, _   = find_peaks(
        -smooth,
        distance=max(6, int(pixels_per_cm * 1.5)),
        height=-threshold
    )
    segments, prev = [], 0
    for g in gaps:
        if (g - prev) > 4:
            segments.append((g - prev) / pixels_per_cm)
        prev = g
    last = w - prev
    if last > 4:
        segments.append(last / pixels_per_cm)
    return segments or [w / pixels_per_cm]


def save_debug_image(img, runs, boxes, tray_x_left, tray_x_right,
                     pixels_per_cm, results, out_path):
    dbg    = img.copy()
    COLORS = [
        (255, 80, 80), (80, 200, 80), (80, 120, 255),
        (255, 200, 0), (200, 0, 200), (0, 200, 200),
        (255, 140, 0), (140, 255, 0),
    ]

    # Tray walls (yellow)
    cv2.line(dbg, (tray_x_left,  0), (tray_x_left,  img.shape[0]), (0, 220, 220), 2)
    cv2.line(dbg, (tray_x_right, 0), (tray_x_right, img.shape[0]), (0, 220, 220), 2)

    # Run bands
    for i, (y0, y1) in enumerate(runs):
        c = COLORS[i % len(COLORS)]
        cv2.rectangle(dbg, (tray_x_left, y0), (tray_x_right, y1), c, 2)
        label = f"Run {i}"
        if i < len(results):
            r = results[i]
            label += f"  TCR={r['TCR']:.0f}%  RQD={r['RQD']:.0f}%"
        cv2.putText(dbg, label, (tray_x_left + 5, y0 + 22),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, c, 2)

    # Pieces: green = counts for RQD, orange = TCR only
    for (x, y, w, h) in boxes:
        length_cm = w / pixels_per_cm
        c = (0, 200, 0) if length_cm >= RQD_MIN_CM else (0, 140, 255)
        cv2.rectangle(dbg, (x, y), (x + w, y + h), c, 1)
        cv2.putText(dbg, f"{length_cm:.1f}cm", (x, max(y - 3, 10)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.30, c, 1)

    cv2.imwrite(out_path, dbg)
    print(f"  [debug] saved → {out_path}")


def compute_tcr_rqd(img_path, debug=False):
    img = cv2.imread(img_path)
    if img is None:
        raise FileNotFoundError(f"Cannot open: {img_path}")

    img = cv2.resize(img, (RESIZE_W, RESIZE_H))
    img_h, img_w = img.shape[:2]

    # Scale
    if TRAY_WIDTH_PX is not None:
        tray_w_px    = TRAY_WIDTH_PX
        tray_x_left  = (img_w - tray_w_px) // 2
        tray_x_right = tray_x_left + tray_w_px
        if debug:
            print(f"  [calibrate] manual tray width: {tray_w_px}px")
    else:
        tray_w_px, tray_x_left, tray_x_right = estimate_tray_width(img, debug)

    pixels_per_cm = tray_w_px / RUN_LENGTH_CM
    if debug:
        print(f"  [scale] {pixels_per_cm:.2f} px/cm")

    boxes, edges  = detect_pieces(img, tray_x_left, tray_x_right)
    runs          = detect_runs(edges, img_h, debug)
    gray_img      = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    results = []
    for run_idx, (y_start, y_end) in enumerate(runs):
        run_pieces = [
            (x, y, w, h) for (x, y, w, h) in boxes
            if y_start <= (y + h // 2) <= y_end
        ]
        lengths_cm = []
        for (x, y, w, h) in run_pieces:
            segs = split_piece(gray_img[y:y+h, x:x+w], pixels_per_cm)
            lengths_cm.extend(segs)

        total = min(sum(lengths_cm), RUN_LENGTH_CM)
        rqd   = min(sum(l for l in lengths_cm if l >= RQD_MIN_CM), total)

        results.append({
            "run":      run_idx,
            "n_pieces": len(run_pieces),
            "TCR":      round((total / RUN_LENGTH_CM) * 100, 2),
            "RQD":      round((rqd   / RUN_LENGTH_CM) * 100, 2),
        })

    if debug:
        base = os.path.splitext(os.path.basename(img_path))[0]
        save_debug_image(img, runs, boxes, tray_x_left, tray_x_right,
                         pixels_per_cm, results, f"debug_{base}.jpg")

    return results


if __name__ == "__main__":
    class Args:
        debug = True        # حط False إلا ما بغيتيش debug images
        calibrate = False

    args = Args()

    image_list = ["Picture1.jpg", "Picture2.jpg", "Picture3.jpg", "Picture4.jpg"]

    for img_name in image_list:
        if not os.path.exists(img_name):
            print(f"[SKIP] {img_name} not found")
            continue

        print(f"\n{'='*40}")
        print(f"Processing: {img_name}")
        print(f"{'='*40}")

        try:
            results = compute_tcr_rqd(img_name, debug=(args.debug or args.calibrate))
            for r in results:
                print(f"  Run {r['run']:2d} | pieces={r['n_pieces']:3d} | "
                      f"TCR={r['TCR']:6.2f}%  RQD={r['RQD']:6.2f}%")
        except Exception as e:
            print(f"  ERROR: {e}")
            import traceback; traceback.print_exc()
