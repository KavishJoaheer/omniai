# syntax=docker/dockerfile:1.7
# Multi-stage build for the Omni-AI backend (FastAPI + arq worker).
#
# Build:   docker build -t omniai-backend:latest backend/
# Run API: docker run -p 9380:9380 omniai-backend:latest
# Run worker: docker run omniai-backend:latest arq omniai.workers.worker.WorkerSettings
#
# The same image runs both the API and the worker; the entrypoint dispatches
# on the OMNIAI_ROLE env var (api | worker | migrate). Migrations always run
# before the API process starts unless OMNIAI_SKIP_MIGRATIONS=1.

# ---- Stage 1: build deps + wheel cache ------------------------------------

FROM python:3.12-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

# Build deps for psycopg, lxml, cryptography, pdfplumber (poppler not needed —
# pdfplumber bundles), Pillow (used by OCR backends).
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        libpq-dev \
        libxml2-dev \
        libxslt1-dev \
        libjpeg-dev \
        zlib1g-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build

# Copy only files needed to resolve dependencies first so this layer caches
# across source changes.
COPY pyproject.toml ./
COPY README.md* ./
RUN python -m venv /opt/venv \
 && /opt/venv/bin/pip install --upgrade pip \
 && /opt/venv/bin/pip install .

# Now copy the source and install in editable mode (or reinstall to bake
# the package metadata).
COPY omniai ./omniai
COPY alembic.ini ./alembic.ini
RUN /opt/venv/bin/pip install --no-deps --force-reinstall .


# ---- Stage 2: runtime ------------------------------------------------------

FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH" \
    OMNIAI_ROLE=api \
    HTTP_PORT=9380

# Runtime libs (no -dev variants). Add tesseract-ocr only if OCR_KIND=tesseract
# is intended; commented out by default to keep the image small.
RUN apt-get update && apt-get install -y --no-install-recommends \
        libpq5 \
        libxml2 \
        libxslt1.1 \
        libjpeg62-turbo \
        curl \
        tini \
    && rm -rf /var/lib/apt/lists/* \
    # Uncomment the next line and `tesseract-ocr-eng` to enable Tesseract OCR.
    # && apt-get install -y --no-install-recommends tesseract-ocr tesseract-ocr-eng \
    && groupadd --system --gid 1001 omniai \
    && useradd  --system --uid 1001 --gid omniai --create-home --home /home/omniai omniai

# Copy the venv (already has the package installed)
COPY --from=builder /opt/venv /opt/venv
# Copy the app source (alembic.ini + omniai/ + migrations live there)
WORKDIR /app
COPY --from=builder /build/omniai ./omniai
COPY --from=builder /build/alembic.ini ./alembic.ini

# Local fs object-store path used when OBJECT_STORE_KIND=local
RUN mkdir -p /app/.omniai-storage && chown -R omniai:omniai /app

# Entrypoint dispatches on OMNIAI_ROLE
COPY docker/entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh

USER omniai
EXPOSE 9380

HEALTHCHECK --interval=15s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -fsS "http://localhost:${HTTP_PORT}/v1/health" || exit 1

# tini reaps zombies properly (matters for arq workers spawning subprocesses).
ENTRYPOINT ["/usr/bin/tini", "--", "/usr/local/bin/entrypoint.sh"]
CMD []
