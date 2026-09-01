"""Vision-first pipeline for scanned and photographed documents.

Two jobs beyond calling the extractor:

1. Concurrency. Every page is an API call now, so serial processing makes a
   40-page document take several minutes. Pages are independent, so a small
   thread pool cuts that to seconds.

2. Continuation stitching. A long table photographed page by page arrives as
   N separate tables. Rejoining them here is far cheaper than asking a human
   to do it in Excel afterwards.
"""

from concurrent.futures import ThreadPoolExecutor
from difflib import SequenceMatcher
from pathlib import Path
from typing import Callable, List, Optional

import config

from . import extract_offline, extract_vision, ingest
from .models import Table


def _headers_match(a: Table, b: Table, threshold: float = 0.85) -> bool:
    if a.n_cols != b.n_cols:
        return False
    norm = lambda hs: " | ".join(h.strip().lower() for h in hs)
    return SequenceMatcher(None, norm(a.headers), norm(b.headers)).ratio() >= threshold


def stitch(tables: List[Table]) -> List[Table]:
    """Merge tables on consecutive pages that share the same headers.

    Conservative on purpose: same column count, near-identical header text,
    consecutive pages, same source file. Two genuinely different tables that
    happen to share headers are rare; a wrongly split table is common.
    """
    if not tables:
        return []

    merged = [tables[0]]
    for current in tables[1:]:
        previous = merged[-1]
        if (current.source_file == previous.source_file
                and current.page == previous.page + 1
                and _headers_match(previous, current)):
            previous.rows.extend(current.rows)
            note = f"continued from p{previous.page} through p{current.page}"
            previous.flags = [f for f in previous.flags if not f.startswith("continued")]
            previous.flags.append(note)
            previous.page_end = current.page
        else:
            merged.append(current)
    return merged


def run(file_path: str, clean: bool = True, stitch_pages: bool = True,
        max_pages: Optional[int] = None, engine: Optional[str] = None,
        on_progress: Optional[Callable[[int, int], None]] = None) -> List[Table]:
    """engine: "offline" (Tesseract, free, private) or "cloud" (vision model).

    Defaults to whatever config says, so the same call works in both builds.
    """
    engine = engine or config.ENGINE
    name = Path(file_path).name
    pages = ingest.load_pages(file_path, clean=clean, max_pages=max_pages)
    total = len(pages)
    done = 0

    def work(page):
        if engine == "offline":
            tables = extract_offline.extract_page(page.image, name, page.number)
        else:
            tables = extract_vision.extract_page(page.png, name, page.number)
        for t in tables:
            t.flags = page.notes + t.flags        # carry image-quality notes through
        return tables

    # Tesseract is CPU-bound and already uses several cores, so piling threads
    # on top of it just causes contention. Network-bound cloud calls are the
    # opposite and want the concurrency.
    workers = 1 if engine == "offline" else config.MAX_WORKERS

    results: List[Table] = []
    with ThreadPoolExecutor(max_workers=min(workers, max(total, 1))) as pool:
        for tables in pool.map(work, pages):
            results.extend(tables)
            done += 1
            if on_progress:
                on_progress(done, total)

    results.sort(key=lambda t: t.page)
    return stitch(results) if stitch_pages else results
