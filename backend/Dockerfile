# ─────────────────────────────────────────────
# Stage 1: Build Vue3 + Vite frontend
# ─────────────────────────────────────────────
FROM node:20-alpine AS frontend-builder

WORKDIR /frontend

# Copy frontend dependency manifests
COPY frontend/package.json frontend/package-lock.json* ./

# Install frontend dependencies
RUN npm install --prefer-offline

# Copy frontend source and build
COPY frontend/ .
RUN npm run build
# Output: /frontend/dist/


# ─────────────────────────────────────────────
# Stage 2: Python runtime + FastAPI
# Python will serve the built frontend as static files
# ─────────────────────────────────────────────
FROM python:3.11-slim AS runtime

# System dependencies for OpenCV and Pillow
RUN apt-get update && apt-get install -y --no-install-recommends \
    libglib2.0-0 \
    libgl1 \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# ── Install Python dependencies ──────────────
# Copy requirements first for layer caching
COPY backend/requirements.txt ./requirements.txt

# Upgrade pip and install dependencies
RUN pip install --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# ── Copy backend source ───────────────────────
COPY backend/ .

# ── Copy built frontend into FastAPI static dir ──
COPY --from=frontend-builder /frontend/dist /app/static

# ── Data directories (will be overridden by volume mounts) ──
RUN mkdir -p data/uploads data/datasets data/augmented data/models data/exports logs

# ── Environment defaults ──────────────────────
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    HOST=0.0.0.0 \
    PORT=8000 \
    DEBUG=false \
    STATIC_DIR=/app/static

EXPOSE 8000

CMD ["python", "run.py"]
