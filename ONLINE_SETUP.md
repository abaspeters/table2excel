# Two versions online, from one GitHub repo

**One repository, two deployments.** They run the same code and differ only by environment variables. Do not copy the project into two repos — you'd fix every bug twice, and within a month the two would behave differently in ways nobody can explain.

| | Standard | AI |
|---|---|---|
| Entry file | `app_standard.py` | `app_ai.py` |
| Reader | Tesseract on the server | Vision model |
| Cost | Free per page | Charged per page |
| Best on | Clear, printed, ruled tables | Poor scans, handwriting, borderless tables |
| API key | **None** | Required |

Two entry files exist for one reason: Streamlit identifies an app by repo + branch + main file, so the same repo can't be deployed twice without them. They set configuration and hand off to the shared `app.py`.

---

## Part 1 — Get the code onto GitHub

### 1. Install Git

Download from `git-scm.com`. Accept the defaults.

### 2. Check what you're about to publish

**Before anything else**, from the project folder:

```
git status
```

If `.env` appears in that list, stop. `.gitignore` already excludes it, but confirm — a key pushed to GitHub is compromised the moment it lands, public repo or not. Bots scan for them within minutes.

### 3. Create the repository

On github.com: **New repository** → name it `table2excel` → **Private** → don't add a README (you have one) → Create.

### 4. Push

```
cd "C:\path\to\table2excel"
git init
git add .
git commit -m "Initial commit"
git branch -M main
git remote add origin https://github.com/YOURNAME/table2excel.git
git push -u origin main
```

GitHub will ask you to sign in through the browser. Refresh the repo page — all your files should be there, and `.env` should not be.

---

## Part 2 — Deploy the Standard version first

Start with this one. It has no API key, so a misconfiguration costs you nothing, and it proves the harder half of the setup — Tesseract on a server — before money is involved.

1. Go to `share.streamlit.io` and sign in with GitHub.
2. **New app** → **Deploy a public app from GitHub** → authorise access to your private repo.
3. Fill in:
   - Repository: `YOURNAME/table2excel`
   - Branch: `main`
   - **Main file path: `app_standard.py`** ← this is the setting that makes it the no-AI version
   - App URL: something like `cinfores-scan2excel`
4. **Advanced settings** → Python version **3.12** → Save.
5. Deploy.

First build takes 5–10 minutes. It's installing Tesseract from `packages.txt` and the Python packages from `requirements.txt`.

**Test it with a real scan before moving on.** If it extracts a table, the hard part is done.

## Part 3 — Deploy the AI version

Same repo, different entry file.

1. **New app** again, same repository and branch.
2. **Main file path: `app_ai.py`**
3. App URL: something like `cinfores-scan2excel-ai`
4. **Advanced settings** → **Secrets**, paste exactly this:

```toml
ANTHROPIC_API_KEY = "sk-ant-your-actual-key-here"
```

TOML format — key, equals, value in double quotes. Not `export`, no colon.

5. Deploy.

If the key is missing or wrong, the app says so on its own start page rather than failing later on an upload. That was deliberate.

---

## Part 4 — Lock it down

**Set a password on both.** Add to each app's Secrets:

```toml
APP_PASSWORD = "something-long-and-not-obvious"
```

Streamlit Community Cloud apps are reachable by anyone with the URL. For the AI app that means anyone who finds it can spend your credits. For the Standard app it means anyone can upload documents to something with your organisation's name on it.

**Set a spending limit** in the Anthropic console. This is the control that still works when everything else is misconfigured. Do it now, not after the first surprising bill.

**Tune the limits** in the AI app's Secrets:

```toml
MAX_PAGES_PER_FILE = "25"
MAX_FILE_MB = "40"
```

25 pages per file is a reasonable starting ceiling. Raise it once you know what a run actually costs you.

---

## Part 5 — Updating

Both apps redeploy automatically when you push:

```
git add .
git commit -m "What changed"
git push
```

Both rebuild within a minute or two. Which is also the argument for one repo: **one push fixes both.**

---

## What will actually go wrong

| Symptom | Cause | Fix |
|---|---|---|
| Standard app: "Tesseract was not found" | `packages.txt` missing from the repo root | Confirm it's pushed — it must be at the top level, not in a subfolder |
| Build fails on `opencv` | Missing system libraries | `packages.txt` includes `libgl1` and `libglib2.0-0` for this reason. Check it pushed. |
| App crashes on a large PDF | Free tier has ~1 GB RAM; denoising big pages is memory-hungry | Lower `MAX_PAGES_PER_FILE`; split large files |
| First visit takes 30+ seconds | Free apps sleep when idle | Normal. Paid hosting (Render, ~$7/mo) avoids it. |
| AI app: "No API key configured" | Secret missing or malformed TOML | Check the quotes and the `=` |
| Both apps show old behaviour after a push | Build failed | Open **Manage app** → logs |

---

## One thing to decide before you share the links

Uploaded files currently sit in the server's temp directory until the platform clears them. On Streamlit Community Cloud that's **US infrastructure you don't control.**

For anonymised or low-sensitivity documents, fine. For student records, staff files or client financials, check your organisation's position before circulating the URL — and if the answer is that data can't leave your infrastructure, that rules out both of these deployments, not just the AI one. `DEPLOY.md` Stage 4 covers self-hosting with Docker, and the Dockerfile already installs Tesseract, so the Standard version works there unchanged.

That question is worth asking now. It's much easier than withdrawing a link people have started using.
