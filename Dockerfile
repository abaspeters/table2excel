# Pin the minor version. "python:3.12" silently moves under you and a patch
# release that changes a wheel is the classic "it worked last month" bug.
FROM python:3.12-slim

# tesseract-ocr powers the no-AI reader. libgl1/libglib2.0-0 are OpenCV's
# runtime dependencies even in the headless build — without them the import
# fails with a libGL error that gives no clue what is actually missing.
RUN apt-get update && apt-get install -y --no-install-recommends \
        tesseract-ocr tesseract-ocr-eng libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy requirements first. Docker caches this layer, so editing your code
# doesn't trigger a full reinstall on every rebuild.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Don't run as root. If the container is ever exposed, this limits the damage.
RUN useradd -m appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 8501

# Lets your host (and Docker itself) tell "starting up" from "wedged".
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8501/_stcore/health')"

CMD ["streamlit", "run", "app.py", "--server.port=8501", "--server.address=0.0.0.0"]
