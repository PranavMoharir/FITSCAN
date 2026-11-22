# One backend image with two build targets (ADR-023, HLD §16.1):
#   api     FastAPI + Uvicorn; applies database migrations before serving. No PDF, OCR or
#           browser libraries: the API only checks the %PDF- signature and size of uploads.
#   worker  Celery worker, plus Playwright with headless Chromium for JavaScript pages,
#           PyMuPDF and pdfplumber for PDFs, Tesseract for scanned resumes, and scikit-learn
#           for the TF-IDF tie-breaker of the match run
# Build one target with:  docker build --target api -t fitscan-api .
#
# Slow layers (packages, browser) come before the application code, so a code change only
# rebuilds the last layer.

FROM python:3.12-slim AS deps

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Install only the runtime dependencies listed in pyproject.toml (test tools are not installed).
COPY pyproject.toml ./
RUN python -c "import tomllib; print('\n'.join(tomllib.load(open('pyproject.toml', 'rb'))['project']['dependencies']))" > /tmp/requirements.txt \
    && pip install -r /tmp/requirements.txt \
    && rm /tmp/requirements.txt

# Run as an unprivileged user. /data/uploads is created here so the `uploads` volume
# inherits this owner the first time it is mounted.
RUN useradd --create-home --uid 1000 app \
    && mkdir -p /data/uploads \
    && chown app:app /data/uploads


FROM deps AS api
# Application code is owned by root, so the app user can read but not change it.
COPY . .
USER app
EXPOSE 8000
# --no-server-header: responses do not announce the server software ("server: uvicorn").
CMD ["sh", "-c", "alembic upgrade head && exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --no-server-header"]


FROM deps AS worker
# Tesseract OCR with English data (OCR_LANGUAGE=eng). Another language needs its package,
# e.g. tesseract-ocr-deu. One OCR thread per process: the worker already runs two processes.
RUN apt-get update \
    && apt-get install -y --no-install-recommends tesseract-ocr tesseract-ocr-eng \
    && rm -rf /var/lib/apt/lists/*
ENV OMP_THREAD_LIMIT=1
# The worker-only Python packages (Playwright, PyMuPDF, pdfplumber, pytesseract, Pillow, scikit-learn) and
# headless Chromium with its system libraries.
ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright
RUN python -c "import tomllib; print('\n'.join(tomllib.load(open('pyproject.toml', 'rb'))['project']['optional-dependencies']['worker']))" > /tmp/worker-requirements.txt \
    && pip install -r /tmp/worker-requirements.txt \
    && rm /tmp/worker-requirements.txt \
    && playwright install --with-deps --only-shell chromium \
    && chmod -R a+rX /ms-playwright \
    && rm -rf /var/lib/apt/lists/*
COPY . .
USER app
CMD ["celery", "-A", "app.worker.celery_app", "worker", "--loglevel=INFO"]
