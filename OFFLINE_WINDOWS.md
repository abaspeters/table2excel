# Offline on Windows — no API, no credits, no internet

Everything runs on the computer in front of you. Nothing is uploaded, nothing is charged.

Your image-cleaning code was already offline — deshadow, deskew, dewarp are pure NumPy and OpenCV. The only piece that needed replacing was the reading step, which is now **Tesseract OCR** driven by OpenCV table-grid detection.

---

## Read this before you install anything

Offline is genuinely free and genuinely private. It is also **less accurate**, and the gap widens as scan quality drops. Measured on the same test page:

| Scan quality | Offline (Tesseract) | What it did |
|---|---|---|
| Clean, ~180 dpi, straight after cleaning | **13/15 cells exact** | Two small slips: `Power BI` → `Power Bl`, `C. Ada` → `Cc. Ada`. Neither was flagged. |
| Noisy JPEG, ~110 dpi | **0/15 exact**, 10 cells flagged unreadable | Correctly refused rather than inventing values. |

Two things to take from that.

**It fails honestly, which is the important part.** On the bad scan the first version of this code produced twelve confident wrong answers, including `B. Okon` read as `8. Okon` at 89% confidence. After adding denoising and a digits-only second pass for numeric columns, the same page produces highlighted blanks instead. A blank you can see costs you ten seconds. A wrong figure you can't see costs you much more.

**It cannot read handwriting.** Not poorly — at all. Tesseract is a printed-text engine. If your scans contain handwritten entries, offline mode will mark those cells unreadable and you will type them in yourself. That may still be fine: the tool does the printed columns and the structure, you fill the handwriting.

**Where the cloud engine is worth its cost:** poor scans, handwriting, borderless tables, and merged cells. Both engines are in the app and you switch with a radio button, so a sensible pattern is offline for the bulk and cloud for the difficult files. If the documents must not leave your building, that decision is already made for you and offline is your only option — plan the scanning quality accordingly.

**The highest-return action is not software.** Tesseract on a 300-dpi flatbed scan is a different tool from Tesseract on a phone photo. If you can influence how pages are captured, do that first — it will beat any amount of tuning.

---

## Setup

Two things to install, then one script.

### 1. Python

Download Python 3.12 from python.org. **During the installer, tick "Add python.exe to PATH."** Miss that tickbox and setup fails with a confusing error — it is far and away the most common problem.

### 2. Tesseract OCR

Download the Windows installer from `https://github.com/UB-Mannheim/tesseract/wiki` — that is the maintained Windows build. Install to the default location (`C:\Program Files\Tesseract-OCR`).

If you need languages beyond English, tick them in the installer under "Additional language data."

### 3. Run setup

Double-click **`setup_windows.bat`**. It checks both installs, builds the environment, installs components, and writes a `.env` file pointing at Tesseract. Takes a few minutes.

It tells you plainly which of the two is missing if either check fails.

### 4. Use it

Double-click **`start.bat`**. Your browser opens at `http://localhost:8501`. Keep the black window open while you work — closing it stops the app.

That is the whole daily routine: `start.bat`, drag files in, review, download.

---

## For a machine with no internet at all

The setup above still downloads Python packages. To install on a completely disconnected machine:

**On a computer that has internet**, double-click **`make_offline_bundle.bat`**.

(`make_offline_bundle.sh` is the same thing for Mac/Linux. On Windows use the `.bat` — a `.sh` file will not run by double-clicking.)

This downloads all 44 Windows packages into a `wheels/` folder. The machine you run it on does **not** need Tesseract, and does not have to be the machine that will use the app — it just needs Python and a connection. Copy the whole project folder to a USB drive, along with the Python and Tesseract installers.

**On the disconnected machine:** install Python and Tesseract from the installers, then run `setup_windows.bat`. It detects the `wheels/` folder and installs from it without touching the network.

After that the app never needs internet again.

---

## Using it well

**The confidence slider is your main control.** Cells the engine is less sure of than the threshold get highlighted rather than guessed at. Default is 65.

- Raise it (75–85) for figures that must be right — payments, marks, quantities. More cells flagged, less chance of a silent error slipping through.
- Lower it (50–55) for rough data capture where you'd rather have a starting point to correct than a lot of blanks.

Start at the default, run twenty real pages, count how many highlighted cells were actually fine, and adjust from there. Twenty pages of your own documents will tell you more than any general advice.

**Keep image cleaning on.** Deshadow, deskew and the OCR-specific denoising are doing a lot of work. The toggle exists for comparison, not for daily use.

**The review step matters more here, not less.** With the cloud engine, an unreadable cell was flagged because a capable reader said it couldn't tell. With Tesseract, some errors arrive confident — `Power Bl` was never flagged. Spot-check the unflagged cells too, especially in the first few files.

---

## When something goes wrong

| Symptom | Cause | Fix |
|---|---|---|
| "Tesseract was not found" | Installed elsewhere, or not on PATH | Set `TESSERACT_PATH` in `.env` to the full path of `tesseract.exe` |
| "Python was not found" | PATH tickbox missed during install | Reinstall Python with the tickbox ticked |
| Whole page comes back unreadable | Scan too poor for OCR | Rescan at 300 dpi. No setting recovers detail that was never captured. |
| Columns run together | No ruling lines, fell back to word positions | Check the flag in the Notes column. Ruled tables work far better — if you control the form design, rule it. |
| Handwritten cells all blank | Expected — Tesseract can't read handwriting | Type them in, or use cloud mode for those files |
| Very slow | Normal: 2–5 seconds a page | Nothing to fix; it's OCR, and it's using your CPU rather than a server |
| Numbers read as text in Excel | Cell had a currency symbol or stray character | Deliberate — a wrong number is worse than a string. Clean the column afterwards. |

---

## A third option, if you have the hardware

A local vision model via **Ollama** (Qwen2.5-VL or similar) sits between the two: much better than Tesseract on messy scans and handwriting, still fully offline and free to run. The costs are real, though — a machine with a decent GPU, several GB of model download, and considerably slower per page than Tesseract.

Worth considering only if offline accuracy is genuinely blocking you and cloud is genuinely not an option. The swap is contained: `extract_offline.py` and `extract_vision.py` have the same interface, so a third `extract_ollama.py` would drop in beside them without touching the rest of the pipeline. Prove the tool is useful first.
