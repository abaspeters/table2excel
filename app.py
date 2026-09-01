"""Upload -> clean -> extract -> review -> download.

Every cell in the output came from a photograph, so review is not a nicety
here, it is the control that makes the numbers trustworthy. The UI is built
around it: cleaned image beside the editable grid, quality warnings surfaced,
illegible cells highlighted, and no way to reach the download button without
passing through it.
"""

import tempfile
from pathlib import Path

import pandas as pd
import streamlit as st

import config
from core import ingest, pipeline
from core.models import UNREADABLE, Table
from core.to_excel import write

st.set_page_config(page_title="Scan → Excel", page_icon="📄", layout="wide")


def gate() -> bool:
    """Shared-password door. Returns True once the user is through.

    Deliberately minimal — this stops a stranger who finds the URL. If you need
    to know WHO uploaded WHAT, put the app behind your identity provider or an
    authenticating reverse proxy instead of extending this.
    """
    if not config.APP_PASSWORD:
        return True
    if st.session_state.get("authed"):
        return True

    st.title("Scanned pages → Excel")
    entered = st.text_input("Password", type="password")
    if entered:
        if entered == config.APP_PASSWORD:
            st.session_state["authed"] = True
            st.rerun()
        else:
            st.error("Incorrect password.")
    return False


if not gate():
    st.stop()

# Always validate. check() already knows which engine is active and only
# reports what matters for it — skipping it for cloud deployments meant a
# missing API key surfaced as a failed upload instead of a clear startup error.
problems = config.check()
if problems:
    st.title("Scanned pages → Excel")
    for problem in problems:
        st.error(problem)
    st.stop()

st.title("Scanned pages → Excel")

with st.sidebar:
    st.header("Settings")

    if config.ALLOW_ENGINE_SWITCH:
        engine = st.radio(
            "Reading engine",
            ["offline", "cloud"],
            index=0 if config.ENGINE == "offline" else 1,
            format_func=lambda e: ("Offline (Tesseract) — free, private"
                                   if e == "offline"
                                   else "Cloud model — better on poor scans"),
            help="Offline runs on the server with no AI model and no cost. It "
                 "reads clean printed tables well, struggles on poor scans, and "
                 "cannot read handwriting at all.")
    else:
        engine = config.ENGINE
        if engine == "offline":
            st.info("**Standard reader.** No AI, no per-page cost. Best on "
                    "clear, printed, ruled tables.")
        else:
            st.info("**AI reader.** Handles poor scans, handwriting and "
                    "borderless tables. Costs per page.")

    if engine == "offline":
        threshold = st.slider(
            "Confidence threshold", 40, 90, config.MIN_CONFIDENCE, 5,
            help="Cells the engine is less sure of than this are highlighted "
                 "for you instead of guessed at. Higher = more highlighting, "
                 "fewer silent mistakes.")
        import core.extract_offline as _off
        _off.MIN_CONFIDENCE = threshold
    elif not config.API_KEY:
        st.error("No API key configured, so the AI reader is unavailable here. "
                 "Switch to offline, or set ANTHROPIC_API_KEY.")

    clean = st.checkbox("Clean images before reading", value=True,
                        help="Flatten uneven lighting, straighten tilt, correct "
                             "perspective. Turn off only to compare results.")
    stitch_pages = st.checkbox("Rejoin tables split across pages", value=True)
    max_pages = st.number_input(
        "Page limit per file", 1, config.MAX_PAGES_PER_FILE,
        config.MAX_PAGES_PER_FILE)
    st.divider()
    if engine == "offline":
        st.caption(f"Runs on this computer. No internet needed and no cost per "
                   f"page — roughly 2-5 seconds a page depending on the machine. "
                   f"Files must be under {config.MAX_FILE_MB} MB.")
    else:
        st.caption(f"Every page is one paid API call. Ceiling is "
                   f"{config.MAX_PAGES_PER_FILE} pages per file and "
                   f"{config.MAX_PAGES_PER_RUN} per run.")

uploads = st.file_uploader(
    "Upload scanned PDFs or photos",
    type=["pdf", "png", "jpg", "jpeg", "webp", "tif", "tiff"],
    accept_multiple_files=True,
)

oversized = [u.name for u in (uploads or [])
             if u.size > config.MAX_FILE_MB * 1024 * 1024]
if oversized:
    st.error(f"Over the {config.MAX_FILE_MB} MB limit: {', '.join(oversized)}. "
             f"Split the file, or raise MAX_FILE_MB and maxUploadSize together.")

ready = bool(uploads) and not oversized

if ready and st.button("Extract tables", type="primary"):
    tables: list[Table] = []
    originals: dict[str, dict] = {}
    cleaned: dict[str, dict] = {}
    bar = st.progress(0.0, text="Starting…")

    for i, upload in enumerate(uploads):
        with tempfile.NamedTemporaryFile(delete=False,
                                         suffix=Path(upload.name).suffix) as tmp:
            tmp.write(upload.getbuffer())
            tmp_path = tmp.name

        def progress(done, total, name=upload.name, idx=i):
            bar.progress((idx + done / total) / len(uploads),
                         text=f"{name} — page {done}/{total}")

        try:
            found = pipeline.run(tmp_path, clean=clean, stitch_pages=stitch_pages,
                                 max_pages=int(max_pages), engine=engine,
                                 on_progress=progress)
            tables.extend(found)
            originals[upload.name] = dict(ingest.render_pages(tmp_path))
            cleaned[upload.name] = {p.number: p.png for p in
                                    ingest.load_pages(tmp_path, clean=clean,
                                                      max_pages=int(max_pages))}
        except Exception as exc:
            # Show the failing file by name and carry on with the rest — one
            # corrupt scan in a batch of twenty should not lose the other
            # nineteen along with everything already paid for.
            st.error(f"{upload.name} failed: {exc}")

    bar.empty()
    st.session_state.update(tables=tables, originals=originals,
                            cleaned=cleaned, edits={})

tables = st.session_state.get("tables", [])

if tables:
    unreadable = sum(str(c).count(UNREADABLE) for t in tables for r in t.rows for c in r)
    c1, c2, c3 = st.columns(3)
    c1.metric("Tables found", len(tables))
    c2.metric("Rows", sum(t.n_rows for t in tables))
    c3.metric("Cells needing a human", unreadable,
              delta="check these" if unreadable else None,
              delta_color="inverse" if unreadable else "off")

    if unreadable:
        st.warning(f"{unreadable} cell(s) could not be read confidently and are "
                   f"marked `{UNREADABLE}`. Type the correct value over each one. "
                   f"Nothing has been guessed — a missing value is deliberate, "
                   f"and these stay highlighted in the Excel file until fixed.")

    for idx, t in enumerate(tables):
        label = f"{t.source_file} · p{t.page_range} · {t.n_rows}×{t.n_cols}"
        needs_eyes = any(UNREADABLE in str(c) for r in t.rows for c in r)
        if needs_eyes:
            label += "  ⚠ unreadable cells"
        with st.expander(label, expanded=needs_eyes):
            if t.flags:
                st.caption(" · ".join(t.flags))

            grid, view = st.columns([3, 2])
            with grid:
                df = pd.DataFrame(t.rows, columns=t.headers)
                st.session_state["edits"][idx] = st.data_editor(
                    df, num_rows="dynamic", use_container_width=True,
                    key=f"editor_{idx}")
            with view:
                which = st.radio("Page image", ["Cleaned", "Original"],
                                 horizontal=True, key=f"img_{idx}",
                                 label_visibility="collapsed")
                store = (st.session_state["cleaned"] if which == "Cleaned"
                         else st.session_state["originals"])
                png = store.get(t.source_file, {}).get(t.page)
                if png:
                    st.image(png, caption=f"{which} — page {t.page}")

    if st.button("Build Excel file", type="primary"):
        final = []
        for idx, t in enumerate(tables):
            df = st.session_state["edits"].get(idx)
            if df is None:
                final.append(t)
                continue
            final.append(Table(
                headers=[str(c) for c in df.columns],
                rows=[["" if pd.isna(v) else str(v) for v in row]
                      for row in df.itertuples(index=False)],
                source_file=t.source_file, page=t.page, method=t.method,
                title=t.title, flags=t.flags, page_end=t.page_end))

        remaining = sum(str(c).count(UNREADABLE) for t in final for r in t.rows for c in r)
        if remaining:
            st.warning(f"Building anyway, but {remaining} `{UNREADABLE}` marker(s) "
                       f"are still in the data.")

        out = Path(tempfile.mkdtemp()) / "extracted_tables.xlsx"
        write(final, str(out))
        st.download_button("Download extracted_tables.xlsx", out.read_bytes(),
                           file_name="extracted_tables.xlsx",
                           mime=("application/vnd.openxmlformats-officedocument"
                                 ".spreadsheetml.sheet"))
