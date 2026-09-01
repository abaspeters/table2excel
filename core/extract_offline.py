"""Fully offline table extraction. No network, no API, no per-page cost.

The trade against the model-based extractor is real and worth stating plainly:
this is a geometry-and-OCR pipeline, not a reader. It does very well on ruled
tables of printed text, worse on borderless layouts, and it cannot read
handwriting at all. What it does have is Tesseract's per-word confidence
score, which is a genuine advantage — every cell arrives with a number saying
how sure the engine was, and anything below the threshold is marked unreadable
rather than passed off as data.

Strategy A (preferred): find the ruling lines with morphology, intersect them
into a grid, OCR each cell in isolation. Isolating the cell is what makes this
accurate — Tesseract given one cell has no chance to run words together across
a column boundary.

Strategy B (fallback): no usable lines, so cluster word bounding boxes into
rows and columns by position.
"""

import re
from dataclasses import dataclass
from typing import List, Optional, Tuple

import cv2
import numpy as np
import pytesseract
from PIL import Image

import config

from .models import UNREADABLE, Table, normalize

if config.TESSERACT_PATH:
    pytesseract.pytesseract.tesseract_cmd = config.TESSERACT_PATH

# Tesseract's confidence runs 0-100. Below this a cell is marked unreadable
# rather than trusted. A blank highlighted cell costs someone ten seconds; a
# confidently wrong digit can cost far more.
MIN_CONFIDENCE = config.MIN_CONFIDENCE

# Single uniform block of text. Correct for an isolated cell — the default
# mode hunts for page structure that isn't there and does worse.
CELL_CONFIG = "--psm 6"

# Second-pass config for columns that are clearly numeric. Restricting the
# alphabet is the single biggest accuracy win available here: it removes every
# chance of reading 8 as B, 0 as O, or a speck of noise as a letter.
DIGIT_CHARS = "0123456789.,-%()/ "
DIGIT_CONFIG = f"--psm 7 -c tessedit_char_whitelist={DIGIT_CHARS}"

NUMERIC_LIKE = re.compile(r"^[\d.,\-%()/ ]+$")


@dataclass
class Grid:
    rows: List[int]          # y coordinates of horizontal rules
    cols: List[int]          # x coordinates of vertical rules
    region: Tuple[int, int, int, int]


def _binarise(gray: np.ndarray) -> np.ndarray:
    """Adaptive threshold, inverted so ink is white for morphology."""
    return cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                 cv2.THRESH_BINARY_INV, 25, 12)


def _lines(binary: np.ndarray, axis: str, min_ratio: float = 0.35) -> np.ndarray:
    """Isolate long runs of ink along one axis.

    Erode with a long thin kernel: only strokes at least `min_ratio` of the
    page long survive, which is exactly the definition of a ruling line and
    excludes every letter.
    """
    h, w = binary.shape
    if axis == "h":
        size = (max(int(w * min_ratio), 10), 1)
    else:
        size = (1, max(int(h * min_ratio), 10))
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, size)
    eroded = cv2.erode(binary, kernel, iterations=1)
    return cv2.dilate(eroded, kernel, iterations=1)


def _positions(mask: np.ndarray, axis: int, min_gap: int = 12) -> List[int]:
    """Collapse a line mask into one coordinate per rule.

    A drawn line is several pixels thick and a scan makes it thicker still, so
    project onto the axis, keep the runs that are clearly lines, and take the
    centre of each.
    """
    profile = mask.sum(axis=axis) / 255
    threshold = profile.max() * 0.4
    if threshold <= 0:
        return []

    hits = np.where(profile > threshold)[0]
    if len(hits) == 0:
        return []

    groups, current = [], [hits[0]]
    for value in hits[1:]:
        if value - current[-1] <= min_gap:
            current.append(value)
        else:
            groups.append(current)
            current = [value]
    groups.append(current)
    return [int(np.mean(g)) for g in groups]


def detect_grid(gray: np.ndarray, min_cells: int = 4) -> Optional[Grid]:
    binary = _binarise(gray)
    h_mask = _lines(binary, "h")
    v_mask = _lines(binary, "v")

    rows = _positions(h_mask, axis=1)
    cols = _positions(v_mask, axis=0)

    if len(rows) < 2 or len(cols) < 2:
        return None
    if (len(rows) - 1) * (len(cols) - 1) < min_cells:
        return None

    return Grid(rows=rows, cols=cols,
                region=(cols[0], rows[0], cols[-1], rows[-1]))


def _ocr_cell(gray: np.ndarray, x0: int, y0: int, x1: int, y1: int,
              pad: int = 3, config: str = CELL_CONFIG) -> Tuple[str, float]:
    """OCR one cell. Returns its text and the mean word confidence.

    The padding crops inward, away from the ruling lines. Leaving them in is a
    classic source of phantom characters — a vertical rule reads as `1` or `l`
    often enough to matter.
    """
    h, w = gray.shape
    x0, y0 = max(x0 + pad, 0), max(y0 + pad, 0)
    x1, y1 = min(x1 - pad, w), min(y1 - pad, h)
    if x1 - x0 < 6 or y1 - y0 < 6:
        return "", 100.0

    cell = gray[y0:y1, x0:x1]

    # Tesseract is trained on roughly 300-dpi text. Small cells upscale well
    # and the accuracy difference on short numeric strings is not subtle.
    if cell.shape[0] < 30:
        scale = 30 / cell.shape[0]
        cell = cv2.resize(cell, None, fx=scale, fy=scale,
                          interpolation=cv2.INTER_CUBIC)

    data = pytesseract.image_to_data(cell, config=config,
                                     output_type=pytesseract.Output.DICT)

    words, confidences = [], []
    for text, conf in zip(data["text"], data["conf"]):
        text = text.strip()
        conf = float(conf)
        if text and conf >= 0:
            words.append(text)
            confidences.append(conf)

    if not words:
        return "", 100.0          # genuinely empty cell, not a failure to read
    return " ".join(words), float(np.mean(confidences))


def _numeric_columns(raw: List[List[str]], threshold: float = 0.6) -> set:
    """Which columns are numeric, judged from the cells that read cleanly.

    Skips the first row, which is usually a text header even in a number
    column, and ignores blanks so a sparse column still gets classified.
    """
    if len(raw) < 2:
        return set()
    numeric = set()
    for c in range(len(raw[0])):
        values = [row[c].strip() for row in raw[1:] if c < len(row) and row[c].strip()]
        if not values:
            continue
        hits = sum(1 for v in values if NUMERIC_LIKE.match(v))
        if hits / len(values) >= threshold:
            numeric.add(c)
    return numeric


def _grid_tables(gray: np.ndarray, grid: Grid, source: str,
                 page: int) -> List[Table]:
    n_rows, n_cols = len(grid.rows) - 1, len(grid.cols) - 1

    # Pass 1 — read everything with the general config.
    raw: List[List[str]] = []
    confidence: List[List[float]] = []
    for r in range(n_rows):
        row, confs = [], []
        for c in range(n_cols):
            text, conf = _ocr_cell(gray, grid.cols[c], grid.rows[r],
                                   grid.cols[c + 1], grid.rows[r + 1])
            row.append(text)
            confs.append(conf)
        raw.append(row)
        confidence.append(confs)

    # Pass 2 — re-read weak cells in numeric columns with a digits-only
    # alphabet. Cheap, and it rescues exactly the cells most worth rescuing:
    # a misread name is obvious to a reader, a misread figure is not.
    rescued = 0
    for c in _numeric_columns(raw):
        for r in range(1, n_rows):
            if confidence[r][c] >= 90 and NUMERIC_LIKE.match(raw[r][c].strip() or "x"):
                continue
            text, conf = _ocr_cell(gray, grid.cols[c], grid.rows[r],
                                   grid.cols[c + 1], grid.rows[r + 1],
                                   config=DIGIT_CONFIG)
            if conf > confidence[r][c] and text.strip():
                raw[r][c], confidence[r][c] = text, conf
                rescued += 1

    low = 0
    for r in range(n_rows):
        for c in range(n_cols):
            if raw[r][c] and confidence[r][c] < MIN_CONFIDENCE:
                raw[r][c] = UNREADABLE
                low += 1

    table = normalize(raw, source, page, "offline-grid")
    if table is None:
        return []
    if rescued:
        table.flags.append(f"{rescued} numeric cell(s) re-read with a "
                           f"digits-only alphabet")
    if low:
        table.flags.append(f"{low} cell(s) below {MIN_CONFIDENCE}% OCR "
                           f"confidence, marked {UNREADABLE}")
    return [table]


def _cluster(values: List[int], tolerance: int) -> List[List[int]]:
    if not values:
        return []
    ordered = sorted(values)
    groups, current = [], [ordered[0]]
    for v in ordered[1:]:
        if v - current[-1] <= tolerance:
            current.append(v)
        else:
            groups.append(current)
            current = [v]
    groups.append(current)
    return groups


def _wordbox_tables(gray: np.ndarray, source: str, page: int) -> List[Table]:
    """Fallback for tables with no ruling lines: infer structure from where
    the words physically sit."""
    data = pytesseract.image_to_data(gray, config="--psm 6",
                                     output_type=pytesseract.Output.DICT)

    words = []
    for i, text in enumerate(data["text"]):
        text = text.strip()
        conf = float(data["conf"][i])
        if not text or conf < 0:
            continue
        words.append({"text": text, "conf": conf,
                      "x": data["left"][i], "y": data["top"][i],
                      "w": data["width"][i], "h": data["height"][i]})
    if len(words) < 6:
        return []

    line_height = int(np.median([w["h"] for w in words]))
    row_groups = _cluster([w["y"] for w in words], tolerance=max(line_height // 2, 6))
    row_centres = [int(np.mean(g)) for g in row_groups]

    # Column edges from where words START. Table columns are left-aligned far
    # more often than not, so word left edges cluster tightly on real columns.
    col_groups = _cluster([w["x"] for w in words], tolerance=line_height * 2)
    col_starts = [min(g) for g in col_groups]
    if len(col_starts) < 2 or len(row_centres) < 2:
        return []

    raw = [["" for _ in col_starts] for _ in row_centres]
    conf_grid = [[[] for _ in col_starts] for _ in row_centres]

    for word in words:
        r = int(np.argmin([abs(word["y"] - c) for c in row_centres]))
        c = int(np.argmin([abs(word["x"] - s) for s in col_starts]))
        raw[r][c] = (raw[r][c] + " " + word["text"]).strip()
        conf_grid[r][c].append(word["conf"])

    low = 0
    for r in range(len(raw)):
        for c in range(len(raw[r])):
            if raw[r][c] and np.mean(conf_grid[r][c]) < MIN_CONFIDENCE:
                raw[r][c] = UNREADABLE
                low += 1

    table = normalize(raw, source, page, "offline-wordbox")
    if table is None:
        return []
    table.flags.append("no ruling lines found — column structure was inferred "
                       "from word positions, so check the column boundaries")
    if low:
        table.flags.append(f"{low} cell(s) below {MIN_CONFIDENCE}% OCR "
                           f"confidence, marked {UNREADABLE}")
    return [table]


def extract_page(image: Image.Image, source_name: str, page: int) -> List[Table]:
    from . import preprocess
    gray = np.asarray(preprocess.ocr_variant(image))
    grid = detect_grid(gray)
    if grid is not None:
        tables = _grid_tables(gray, grid, source_name, page)
        if tables:
            return tables
    return _wordbox_tables(gray, source_name, page)
