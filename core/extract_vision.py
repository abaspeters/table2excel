"""Path B — scanned PDFs and photographs. Handles merged cells, rotated
scans, handwriting and borderless layouts that defeat rule-based parsers.

The whole accuracy of this path lives in the prompt below. Two rules matter
more than the rest: force rectangular output, and forbid the model from
tidying the data. A model that "helpfully" reformats 1,234.50 into 1234.5 or
expands an abbreviation has silently corrupted the source document.
"""

import base64
import json
from typing import List, Tuple

import config

from .models import UNREADABLE, Table, normalize


def _client():
    """Imported lazily so tests and the Excel writer run with no SDK installed."""
    from anthropic import Anthropic
    return Anthropic()

MODEL = config.MODEL

SYSTEM_PROMPT = f"""You are a table extraction engine reading a SCANNED or PHOTOGRAPHED
page. The image may be imperfect: faint print, scanner streaks, staple marks,
handwriting, stamps, or a slight residual tilt. Read what is on the page.

You output JSON and nothing else. Return exactly this shape:

{{"tables": [{{"title": "string or null",
              "headers": ["..."],
              "rows": [["..."], ["..."]],
              "continues_from_previous_page": true or false}}]}}

TRANSCRIPTION RULES
1. Transcribe every cell EXACTLY as printed. Keep thousands separators,
   currency symbols, percent signs, leading zeros, trailing full stops,
   parentheses around negatives, and the original casing. Never convert,
   round, reformat, translate, correct a spelling, or expand an abbreviation.
2. Handwritten entries are data — transcribe them like printed ones.
3. If a cell is unclear, output "{UNREADABLE}". NEVER guess a value and never
   infer one from the pattern of the surrounding rows. A cell marked
   "{UNREADABLE}" gets checked by a human; a plausible invention does not.
4. Distinguish characters that scans confuse: 0/O, 1/l/I, 5/S, 8/B, 6/G.
   If you cannot tell in a numeric column, use "{UNREADABLE}".
5. A struck-through value that has been corrected: give the correction.

STRUCTURE RULES
6. Every row must have exactly as many entries as `headers`. An empty cell
   is "".
7. Vertically merged cell: repeat its value in each row it spans.
   Horizontally merged cell: put the value leftmost and "" in the rest.
8. Two header rows: flatten to one, joining with " - " (e.g. "2024 - Q1").
9. If the page starts mid-table with no header row of its own, invent NO
   headers — use the first data row's column count, set headers to the
   column labels if any are visible and "" otherwise, and set
   "continues_from_previous_page": true.
10. Ignore page headers, footers, page numbers, signatures and body
    paragraphs. Extract tabular data only.
11. If the image contains no table, return {{"tables": []}}.

Output raw JSON. No markdown fences, no commentary."""


def _parse(text: str) -> dict:
    text = text.strip()
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.lstrip().lower().startswith("json"):
            text = text.lstrip()[4:]
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1:
        raise ValueError(f"No JSON object in model output: {text[:200]}")
    return json.loads(text[start:end + 1])


def extract_page(png_bytes: bytes, source_name: str, page: int,
                 client=None) -> List[Table]:
    client = client or _client()
    response = client.messages.create(
        model=MODEL,
        max_tokens=8000,
        system=SYSTEM_PROMPT,
        messages=[{
            "role": "user",
            "content": [
                {"type": "image",
                 "source": {"type": "base64", "media_type": "image/png",
                            "data": base64.standard_b64encode(png_bytes).decode()}},
                {"type": "text", "text": "Extract all tables from this page."},
            ],
        }],
    )

    text = "".join(b.text for b in response.content if b.type == "text")
    payload = _parse(text)

    out: List[Table] = []
    for entry in payload.get("tables", []):
        headers = entry.get("headers") or []
        rows = entry.get("rows") or []
        if not headers or not rows:
            continue
        table = normalize([headers] + rows, source_name, page, "vision",
                          title=entry.get("title"))
        if table is None:
            continue
        if entry.get("continues_from_previous_page"):
            table.flags.append("model says this continues from the previous page")
        n_bad = sum(1 for r in table.rows for c in r if UNREADABLE in c)
        if n_bad:
            table.flags.append(f"{n_bad} illegible cell(s) marked {UNREADABLE}")
        out.append(table)
    return out


def extract(pages: List[Tuple[int, bytes]], source_name: str) -> List[Table]:
    client = _client()
    results: List[Table] = []
    for page, png in pages:
        results.extend(extract_page(png, source_name, page, client=client))
    return results
