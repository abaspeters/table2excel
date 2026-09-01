"""Common table representation. Every extractor returns these, so the
Excel writer never needs to know how a table was obtained."""

from dataclasses import dataclass, field
from typing import List, Optional

# Marker the extractor writes into any cell it could not read with confidence.
# Lives here, not in the extractor, because the Excel writer keys its
# highlighting off it and must not import the API layer to find out.
UNREADABLE = "<?>"


@dataclass
class Table:
    headers: List[str]
    rows: List[List[str]]
    source_file: str
    page: int
    method: str                      # "pdfplumber-lines" | "pdfplumber-text" | "vision"
    title: Optional[str] = None
    flags: List[str] = field(default_factory=list)
    page_end: Optional[int] = None      # set when pages are stitched together

    @property
    def page_range(self) -> str:
        return f"{self.page}-{self.page_end}" if self.page_end else str(self.page)

    @property
    def n_cols(self) -> int:
        return len(self.headers)

    @property
    def n_rows(self) -> int:
        return len(self.rows)


def _clean(cell) -> str:
    if cell is None:
        return ""
    return " ".join(str(cell).split())


def _dedupe_headers(headers: List[str]) -> List[str]:
    seen, out = {}, []
    for i, h in enumerate(headers):
        # An unreadable header is a missing header. Carrying the marker up here
        # would give several columns the same name and force ugly "<?> (2)"
        # suffixes on what is really just "we could not read the title".
        if not h or UNREADABLE in h:
            h = f"Column {i + 1}"
        if h in seen:
            seen[h] += 1
            h = f"{h} ({seen[h]})"
        else:
            seen[h] = 0
        out.append(h)
    return out


def normalize(raw_rows: List[List], source_file: str, page: int, method: str,
              title: Optional[str] = None, header_row: bool = True) -> Optional[Table]:
    """Turn a ragged list-of-lists into a rectangular Table.

    Returns None for anything too small to be a real table. Every deviation
    it has to correct is recorded as a flag so the review step can surface it.
    """
    grid = [[_clean(c) for c in row] for row in raw_rows if row is not None]
    grid = [r for r in grid if any(c for c in r)]          # drop blank rows
    if len(grid) < 2:
        return None

    flags: List[str] = []
    widths = {len(r) for r in grid}
    width = max(widths)
    if len(widths) > 1:
        flags.append(f"ragged rows: widths {sorted(widths)} padded to {width}")
    grid = [r + [""] * (width - len(r)) for r in grid]

    # Drop columns that are empty top to bottom (a common pdfplumber artefact)
    keep = [i for i in range(width) if any(r[i] for r in grid)]
    if len(keep) < width:
        flags.append(f"dropped {width - len(keep)} empty column(s)")
        grid = [[r[i] for i in keep] for r in grid]

    if len(grid) < 2 or len(grid[0]) < 2:
        return None

    if header_row:
        headers, rows = _dedupe_headers(grid[0]), grid[1:]
    else:
        headers = [f"Column {i + 1}" for i in range(len(grid[0]))]
        rows = grid

    if not rows:
        return None
    if any(h.startswith("Column ") for h in headers):
        flags.append("some headers were blank and auto-named")

    return Table(headers=headers, rows=rows, source_file=source_file, page=page,
                 method=method, title=title, flags=flags)
