# Scanned pages → Excel: build guide

> **Two engines.** `core/extract_offline.py` runs entirely on your machine via Tesseract — free, private, no internet. `core/extract_vision.py` uses a cloud vision model — better on poor scans and handwriting, costs per page. Same interface, switchable in the app. For Windows offline setup and an honest accuracy comparison see **OFFLINE_WINDOWS.md**; for hosting see **DEPLOY.md**.

Every input here is a photograph or scan. That single fact decides the whole design, so start there.

---

## What changes when everything is a scan

There is no text layer to parse. No coordinates, no ruling-line geometry, no `pdfplumber`. The PDF is just a thin wrapper around one JPEG per page. So the geometric-parser path is gone, and three things that were secondary become the whole game:

| Priority | Why |
|---|---|
| **1. Image quality** | The highest-leverage code in the project. A vision model reading a shadowed, tilted phone photo makes far more transcription errors than the same model reading a flattened, deskewed version of the *identical page*. Nothing else buys as much accuracy per line of code. |
| **2. Handling uncertainty honestly** | Scans have faint print, staple marks, handwriting, 0-vs-O ambiguity. The model must mark what it cannot read instead of guessing plausibly. |
| **3. Cost and time** | Every page is now an API call. Serial processing of a 40-page file takes minutes. |

Pipeline:

```
upload → extract page at native resolution → dewarp → deshadow → deskew → enhance
       → vision model (parallel) → normalise → stitch split tables
       → human review → Excel
```

---

## Step 1 — Set up

```bash
python -m venv .venv && source .venv/bin/activate    # Windows: .venv\Scripts\activate
pip install -r requirements.txt
export ANTHROPIC_API_KEY=sk-ant-...
streamlit run app.py
```

Only OpenCV is optional (it adds perspective correction). Everything else is pure Python wheels — no Poppler, no Tesseract, no JVM.

## Step 2 — Get the image out without degrading it (`core/ingest.py`)

This step is easy to get wrong in a way that silently costs you accuracy.

A scanner app produces a PDF containing one JPEG per page. If you render that PDF at a fixed DPI, you resample someone else's JPEG twice — once when the viewer scales it onto the page, once when you rasterise. **Pick too low a DPI and you throw away detail that was really there; too high and you upscale a small JPEG into a blurry big one and pay to send the extra pixels.**

So the code pulls the embedded image out at its **native resolution** via `pypdf`, and only falls back to rendering when the page isn't a single full-page scan:

```python
dpi_x = embedded.width  / (page_width_pt  / 72)
dpi_y = embedded.height / (page_height_pt / 72)
```

That derived DPI is also a free quality signal. Below ~150 DPI, small digits become unreliable and the page gets flagged so the reviewer knows to look harder. Tested on a scanner-app PDF it reports the source resolution exactly.

## Step 3 — Clean the page (`core/preprocess.py`)

Four operations, in a deliberate order. **The order is not arbitrary and getting it wrong costs you real accuracy** — see the measured result below.

**Dewarp** (OpenCV, optional). Finds the page's four corners and flattens it to a rectangle — for photos taken at an angle. It only fires when it finds a convincing quadrilateral covering a large share of the frame, and returns nothing when unsure, so a bad crop can't silently replace a usable photo.

**Deshadow.** The most common phone-photo defect is uneven lighting. Estimate the background by heavily blurring the page (text is small and high-frequency so it blurs away; the shadow gradient survives), then divide the original by that background:

```python
flat = np.clip(gray / np.maximum(blurred_gray, 1) * 255, 0, 255)
```

Measured on a synthetic page with a strong lighting gradient: before, 30.7% of pixels looked like ink and the page's median brightness was 152. After, the background is a uniform 254 and only the actual 1.5% of ink pixels are dark.

**Deskew.** Rotate and measure the variance of the horizontal projection profile. When text lines are level each row is either mostly ink or mostly blank, so the profile is spiky and its variance peaks; tilted text smears ink across every row and flattens it. Coarse pass then fine pass on a downscaled copy — about 30 cheap rotations instead of 80 expensive ones. On a page tilted 4.3°, it recovers 4.2°.

**Here is why the order matters:** run deskew *before* deshadow on that same shadowed page and the estimate runs to the limit of its range at −9.0° — completely wrong — because a global threshold on a shadowed page marks the whole dark side as "ink". Deshadow first and it lands on +4.2°. (The code now deshadows a working copy inside the skew estimator too, so `deskew()` is safe to call standalone.)

**Enhance.** Contrast stretch plus unsharp mask. Deliberately stops short of binarisation — thresholding to pure black and white destroys faint pencil marks, carbon-copy text and light table rules that a vision model can still read from greyscale.

## Step 4 — Read the page (`core/extract_vision.py`)

The prompt is where accuracy lives. Beyond forcing rectangular output, three rules earn their place specifically because these are scans:

1. **Never guess, ever.** Unclear cell → `<?>`. And explicitly: never infer a value from the pattern of surrounding rows. A cell marked `<?>` gets checked by a human; a plausible invention does not. This is the difference between a tool you can trust and one you can't.
2. **Name the confusable characters.** 0/O, 1/l/I, 5/S, 8/B, 6/G. If it can't tell in a numeric column, `<?>`.
3. **Never tidy.** No rounding, no reformatting `1,234.50` to `1234.5`, no expanding `LGA`. `temperature=0` keeps it consistent.

It also handles handwriting as data, struck-through corrections, and flags a page that starts mid-table.

## Step 5 — Stitch tables split across pages (`core/pipeline.py`)

A long ledger photographed page by page arrives as N separate tables. Rejoining them in code is far cheaper than asking someone to do it in Excel afterwards.

The rule is deliberately conservative: same source file, consecutive pages, same column count, header text ≥85% similar. Two genuinely different tables that happen to share headers are rare; a wrongly-split table is common. Verified: it merges pages 1–2 of a ledger, leaves page 3's different table alone, and never merges across files.

Pages also run through a 4-thread pool, since they're independent and each is a network round-trip.

## Step 6 — Review (`app.py`)

**Do not ship this without the review step.** When every cell came from a photograph, review is the control that makes the numbers trustworthy — it is not a nicety.

The UI shows the editable grid beside the page image, with a toggle between the cleaned and original versions (useful when you're deciding whether the model misread or the scan is genuinely illegible). Tables containing `<?>` auto-expand, a counter shows how many cells need a human, and the download warns if any markers are still unresolved.

## Step 7 — Write the Excel (`core/to_excel.py`)

**Every cell the extractor could not read gets a faint amber fill, a thin amber border, dark bold text, and a hover comment naming the source file and page.** The `_Index` sheet counts them per table and a legend at the bottom explains the shading, so someone opening the file next year doesn't have to ask what it means.

The highlight is keyed off the cell's **text**, not off a position recorded during extraction. That matters: fix a cell in the review editor and the highlight disappears on its own; miss one and it stays lit. A position-based approach would go stale the moment anyone inserted a row.

One table per sheet, plus an `_Index` sheet carrying source file, page range, and every quality flag — so a row reads like:

> `Results · scanned.pdf · p1 · native scan ~180 dpi; lighting flattened; deskewed +4.2°; 1 illegible cell marked <?>`

Six months later, that is what tells you whether to trust a number.

Type coercion is conservative: `45,000.00` becomes a real number formatted `#,##0.00`; `12.5%` becomes `0.125` formatted `0.0%`. Anything with a currency symbol, a stray letter, or a `<?>` marker stays as text. A wrong number is worse than a string.

---

## Where it will break

| Symptom | Cause | Fix |
|---|---|---|
| Small digits misread | Scan below ~150 DPI | Nothing downstream fixes lost pixels — rescan at 300 DPI. The flag tells you when this is the cause. |
| Deskew makes it worse | Page is mostly a photo or a form with few text lines | Lower `limit` in `estimate_skew`, or disable cleaning for that file |
| Dewarp crops the table | Detected the wrong quadrilateral | Raise `min_area_ratio`; it already declines when unsure |
| Faint carbon copies vanish | Over-aggressive contrast | Lower `cutoff` in `enhance()` |
| JSON truncated mid-table | Table exceeds `max_tokens` | Raise it, or split the page image horizontally |
| Rotated 90°/180° | Deskew only corrects ±8° | Detect orientation first, then `img.rotate(90)` |
| Costs climbing | Every page is a call | Route clean, high-DPI scans through a cheaper model tier; keep the top tier for hard pages |

## Adapting it

- **Batch, no UI:** `pipeline.run()` then `to_excel.write()`. The UI is a thin layer over those two calls.
- **API service:** wrap both in FastAPI. Add a job queue once files get long — 40 pages is 40 round-trips.
- **n8n:** Read Binary File → HTTP Request to a FastAPI wrapper → Convert to File. Keep extraction in Python; n8n orchestrates, it doesn't parse.
- **Recurring document types.** This is the biggest available win. If it's always the same result sheet or the same supplier's invoice, add a template layer: known expected columns, known value ranges, known row-count patterns. Then you can validate an extraction automatically and only route failures to a human — which is what turns this from a tool someone babysits into one that runs unattended.
