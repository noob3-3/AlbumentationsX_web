# ╔══════════════════════════════════════════════════════════════╗
# ║  AlbumentationsX Training Platform — All-in-one Dockerfile  ║
# ║  Multi-stage: frontend build → Python runtime               ║
# ║  Run from project root: docker build -t axweb .             ║
# ╚══════════════════════════════════════════════════════════════╝

# ─────────────────────────────────────────────
# Stage 1: Build Vue3 + Vite frontend
# ─────────────────────────────────────────────
FROM node:20-alpine AS frontend-builder

WORKDIR /frontend

# Cache npm install layer separately
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm install --prefer-offline

# Build production bundle
COPY frontend/ .
RUN npm run build
# Artifacts at /frontend/dist/


# ─────────────────────────────────────────────
# Stage 2: Install Python dependencies
# Use a separate stage so pip cache can be reused
# independently of source code changes.
# ─────────────────────────────────────────────
FROM python:3.11-slim AS python-builder

# Build tools needed for some packages (e.g. numpy, opencv)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    libglib2.0-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /install

COPY backend/requirements.txt .

RUN pip install --upgrade pip && \
    pip install --no-cache-dir --prefix=/install/deps -r requirements.txt


# ─────────────────────────────────────────────
# Stage 3: Final runtime image
# Python serves both the API and the built frontend
# ─────────────────────────────────────────────
FROM python:3.11-slim AS runtime

LABEL maintainer="AlbumentationsX Platform"
LABEL description="Object detection data collection, augmentation and training platform"

# Runtime system libraries (OpenCV, Pillow, etc.)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libglib2.0-0 \
    libgl1 \
    libgomp1 \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# ── Copy installed Python packages from builder ──
COPY --from=python-builder /install/deps /usr/local

# ── Copy FastAPI application source ──────────
COPY backend/ .

# ── Copy built frontend static files ─────────
# FastAPI will serve these under "/" via StaticFiles
COPY --from=frontend-builder /frontend/dist /app/static

# ── Persistent data directories ──────────────
# Override with named volumes in docker-compose
# Set permissions to 777 to allow both host and container to read/write
RUN mkdir -p \
    data/uploads \
    data/datasets \
    data/augmented \
    data/models \
    data/exports \
    logs && \
    chmod -R 777 data logs

# ── Python environment ────────────────────────
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    HOST=0.0.0.0 \
    PORT=8000 \
    DEBUG=false \
    STATIC_DIR=/app/static \
    DATABASE_URL=sqlite:///./data/app.db

EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=20s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

CMD ["python", "run.py"]
