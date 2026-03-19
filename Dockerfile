# ── Stage 1: Builder ──────────────────────────────────────────────────────────
# This stage installs dependencies. It has pip and build tools.
# We throw this stage away — only the installed packages survive to stage 2.
FROM python:3.12-slim AS builder

WORKDIR /app

# Copy requirements FIRST — before any code.
# Why: Docker caches each instruction as a layer. If requirements.txt hasn't
# changed, Docker reuses the cached pip install layer and skips it entirely.
# Copying code first would bust this cache on every code change.
COPY requirements.txt .

# Install dependencies into a separate directory (/install).
# --prefix=/install keeps them isolated so we can copy just this folder
# into the runtime stage cleanly.
# --no-cache-dir reduces image size by not storing the pip download cache.
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt


# ── Stage 2: Runtime ──────────────────────────────────────────────────────────
# Fresh, minimal base. No pip, no build tools, no cache. Smaller + more secure.
FROM python:3.12-slim

WORKDIR /app

# Copy only the installed packages from the builder stage.
# Everything else from the builder (pip, gcc, cache) is left behind.
COPY --from=builder /install /usr/local

# Copy application source code.
# .dockerignore controls what gets included (venv, tests, .git are excluded).
COPY . .

# Expose the port uvicorn will listen on.
# EXPOSE is documentation — it doesn't actually open the port.
# The actual port mapping happens in docker-compose or docker run -p.
EXPOSE 8000

# Health check: Docker will ping /health every 30s.
# If it fails 3 times, the container is marked unhealthy.
# Railway and AWS ECS use this to know when the app is ready.
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"

# Default command to start the app.
# JSON array format (not shell string) — handles signals correctly so
# Docker can gracefully shut down the container (SIGTERM → uvicorn shutdown).
# --host 0.0.0.0 — listen on all interfaces inside the container, not just localhost.
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]
