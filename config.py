"""All deployment knobs in one place, read from the environment.

Nothing here is a secret except the API key, and that never gets a default —
a missing key should fail loudly at startup, not silently at the first upload.
"""

import os


def _int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except ValueError:
        return default


# --- Access -----------------------------------------------------------------
# Set APP_PASSWORD to put the app behind a shared password. Leave it unset for
# a machine only you use. This is a doorlock, not real authentication: it stops
# a stranger who finds the URL, it does not give you per-user accounts.
APP_PASSWORD = os.environ.get("APP_PASSWORD", "")

# --- Engine -----------------------------------------------------------------
# "offline" = Tesseract on this machine: free, private, no network.
# "cloud"   = vision model: far better on poor scans and handwriting, costs
#             per page and sends the image off the machine.
ENGINE = os.environ.get("ENGINE", "offline")

# When false, the app is locked to ENGINE and the picker is hidden. This is
# what makes the free deployment genuinely free: with no key present AND no
# way to switch, there is no path from that URL to your API balance.
ALLOW_ENGINE_SWITCH = os.environ.get("ALLOW_ENGINE_SWITCH", "true").lower() \
    not in ("false", "0", "no")

# Windows: point this at tesseract.exe if it isn't on PATH.
TESSERACT_PATH = os.environ.get("TESSERACT_PATH", "")

# Tesseract confidence below which a cell is marked unreadable instead of
# trusted. Raising it flags more cells (more manual checking, fewer silent
# errors); lowering it does the reverse. See DEPLOY notes before changing.
MIN_CONFIDENCE = _int("MIN_CONFIDENCE", 65)

# --- Model ------------------------------------------------------------------
API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
MODEL = os.environ.get("EXTRACTION_MODEL", "claude-sonnet-5")

# --- Limits -----------------------------------------------------------------
# Every page is a paid API call, so these are cost controls, not just guardrails.
MAX_PAGES_PER_FILE = _int("MAX_PAGES_PER_FILE", 40)
MAX_PAGES_PER_RUN = _int("MAX_PAGES_PER_RUN", 120)
MAX_FILE_MB = _int("MAX_FILE_MB", 50)
MAX_WORKERS = _int("MAX_WORKERS", 4)


def check() -> list[str]:
    """Startup validation. Returns a list of problems, empty if healthy."""
    problems = []
    if ENGINE == "cloud" and not API_KEY:
        problems.append(
            "ENGINE is set to 'cloud' but ANTHROPIC_API_KEY is not set. Either "
            "add the key, or set ENGINE=offline to use Tesseract on this "
            "machine instead.")
    if ENGINE == "offline":
        problems.extend(_check_tesseract())
    if MAX_PAGES_PER_RUN < MAX_PAGES_PER_FILE:
        problems.append(
            f"MAX_PAGES_PER_RUN ({MAX_PAGES_PER_RUN}) is below "
            f"MAX_PAGES_PER_FILE ({MAX_PAGES_PER_FILE}); a single allowed file "
            f"would be rejected.")
    return problems


def _check_tesseract() -> list[str]:
    """Confirm Tesseract is actually reachable.

    Worth doing at startup rather than on first upload: on Windows the usual
    failure is an installer that didn't add itself to PATH, and the error you
    get mid-upload names a DLL rather than the real problem.
    """
    try:
        import pytesseract
    except ImportError:
        return ["pytesseract is not installed. Run: pip install pytesseract"]

    if TESSERACT_PATH:
        pytesseract.pytesseract.tesseract_cmd = TESSERACT_PATH

    try:
        pytesseract.get_tesseract_version()
    except Exception:
        return [
            "Tesseract was not found. Install it, then either add it to PATH "
            "or set TESSERACT_PATH in your .env file — on Windows that is "
            r"usually C:\\Program Files\\Tesseract-OCR\\tesseract.exe"]
    return []
