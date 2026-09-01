# Turning this into an app people can use

Five stages. Stop at whichever one matches who actually needs to use it — going further than you need adds cost and maintenance for nothing.

| Stage | Who can use it | Effort |
|---|---|---|
| 1. Runs on your machine | You | 10 min |
| 2. Runs on a colleague's machine | Anyone you hand it to | +20 min |
| 3. On the internet, password-protected | Your team, from anywhere | +30 min |
| 4. On your own server | Your team, data never leaves your infrastructure | +1–2 hrs |
| 5. Hardened for real operation | Same, but survives contact with reality | ongoing |

---

## Stage 1 — Run it on your machine

```bash
cd table2excel
cp .env.example .env          # then edit .env and paste your API key
./run.sh                      # Windows: double-click run.bat
```

`run.sh` creates the virtual environment, installs dependencies, loads `.env` and launches. Browser opens at `http://localhost:8501`.

**Get your API key** at console.anthropic.com → API Keys. Put it in `.env`, never in the code. `.gitignore` already excludes `.env`, which is the one line standing between you and a key leaked into a public repo.

**Test with 3–5 of your real scans before anything else.** Not clean samples — your worst ones. Everything after this stage is wasted effort if the extraction quality isn't there, and you'll learn more from five real pages than from any amount of planning.

## Stage 2 — Make it runnable by a non-technical colleague

The blocker is Python. Two honest options:

**Option A — install Python on their machine** (30 min, free). Install Python 3.12 from python.org, **tick "Add Python to PATH"** during install (the single most common failure), copy the folder over, double-click `run.bat`. Fine for two or three people. It does not scale — you will be doing desk visits.

**Option B — skip to Stage 3.** Once more than about three people need it, hosting it centrally is less work than installing Python repeatedly, not more. Most people over-invest in Option A before accepting this.

Either way your API key is now on someone else's machine. If that bothers you, that's Stage 3 or 4 talking.

## Stage 3 — Put it online with a password

**Set a password first.** In `.env`:

```
APP_PASSWORD=something-long-and-not-guessable
```

Without it, anyone who finds the URL can spend your API credits. This is a doorlock, not authentication — it stops strangers, it doesn't tell you who uploaded what.

**Push to a private GitHub repo:**

```bash
git init && git add . && git commit -m "Initial commit"
# create a PRIVATE repo on github.com, then:
git remote add origin https://github.com/YOURNAME/table2excel.git
git push -u origin main
```

Check `git status` shows no `.env` before you push. If it does, stop and fix `.gitignore`.

**Then pick a host:**

| Host | Cost | Notes |
|---|---|---|
| **Streamlit Community Cloud** | Free | Easiest by far. Connect the repo, put your key in the Secrets panel. Sleeps when idle, so first load after a quiet spell is slow. Fine for internal use. |
| **Render** | ~$7/mo | Uses your Dockerfile directly. Doesn't sleep on paid tiers. Good middle ground. |
| **Railway / Fly.io** | ~$5/mo | Similar. Fly puts it closer to Nigerian users, which matters for uploading large scans. |

On all three: **never paste the API key into a file you commit.** Every one of them has an environment-variables or secrets panel — that's where it goes.

**Watch the upload limit.** Scanned PDFs are large. `maxUploadSize` in `.streamlit/config.toml` and `MAX_FILE_MB` in `config.py` must be raised together — raising one alone produces a confusing half-failure.

## Stage 4 — Your own server

Choose this when documents can't leave your infrastructure — which for student records, staff files or client financials may not be your decision to make. Check before you deploy, not after.

```bash
# On the server (Ubuntu 22.04+)
git clone https://github.com/YOURNAME/table2excel.git
cd table2excel
cp .env.example .env && nano .env       # paste key and password
docker compose up -d
```

That's the whole deployment. `restart: unless-stopped` brings it back after a reboot.

Then put a reverse proxy in front for HTTPS — Caddy is the shortest path:

```
scan2excel.yourdomain.com {
    reverse_proxy localhost:8501
}
```

Caddy gets and renews the certificate automatically. **Do not skip HTTPS.** Without it the password and every uploaded document cross the network in the clear.

Useful commands: `docker compose logs -f` to watch, `docker compose pull && docker compose up -d --build` to update.

## Stage 5 — Hardening

These are the things that bite after launch, roughly in the order they will.

**Cost control.** Every page is a paid call, so a colleague uploading a 400-page file is a real bill. `MAX_PAGES_PER_FILE`, `MAX_PAGES_PER_RUN` and `MAX_FILE_MB` are already enforced — tune them to what you're willing to spend. Then set a **monthly spend limit in the Anthropic console**, which is the only control that works when the in-app one is bypassed or misconfigured.

**Know what it costs you.** Log pages processed per run and reconcile against console usage weekly for the first month. Until you've done that you're guessing, and guessing is how people discover the bill.

**Real accounts, if you need them.** The shared password can't tell you who uploaded what. If you need that — and for student or staff records you may be required to — put an authenticating proxy (Authelia, or Cloudflare Access) in front rather than extending `gate()`. Don't build authentication yourself.

**Uploaded files.** They currently go to the system temp directory and stay until the OS clears them. On a shared server that's a pile of other people's documents sitting on disk. Delete them in a `finally` block after processing, and check your host's data-retention terms.

**Concurrency.** Streamlit handles a handful of simultaneous users comfortably. Past that, page-level threads from several users compete and everyone's run gets slower. The fix is a job queue, not a bigger server — but don't build one until you actually see the problem.

**Model version.** `EXTRACTION_MODEL` is configurable for a reason. When you change it, re-run the same sample documents and compare before switching everyone over. Extraction accuracy is the whole product; don't let it change silently underneath you.

---

## Recommended path

Given a training and education setting, I'd go: **Stage 1 today with your real scans → Stage 3 on Streamlit Community Cloud with a password → Stage 4 only if a records-handling rule requires it.**

The reason to resist jumping straight to Stage 4: Stage 3 is free and takes an afternoon, and it tells you whether people actually use the thing. Plenty of internal tools get a server, a domain and a deployment pipeline before anyone discovers the workflow doesn't fit how the work is really done.
