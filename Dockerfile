# ============================================================
# Stage 1: Builder — install dependencies into a wheel cache
# ============================================================
FROM python:3.12-slim AS builder

WORKDIR /build

COPY requirements.txt .
RUN pip install --no-cache-dir --user --upgrade pip && \
    pip install --no-cache-dir --user -r requirements.txt

# ============================================================
# Stage 2: Runtime — minimal image with only what's needed
# ============================================================
FROM python:3.12-slim AS runtime

ARG VERSION=1.0.0-rc.1
ARG BUILD_DATE
ARG GIT_COMMIT
ARG PYTHON_VERSION=3.12

LABEL org.opencontainers.image.title="AI Router Gateway"
LABEL org.opencontainers.image.description="Production-ready AI Gateway with intelligent routing, health checks, and fallback"
LABEL org.opencontainers.image.version="${VERSION}"
LABEL org.opencontainers.image.created="${BUILD_DATE}"
LABEL org.opencontainers.image.revision="${GIT_COMMIT}"
LABEL org.opencontainers.image.url="https://github.com/anomalyco/ai-router"
LABEL org.opencontainers.image.source="https://github.com/anomalyco/ai-router"
LABEL org.opencontainers.image.documentation="https://github.com/anomalyco/ai-router#readme"
LABEL org.opencontainers.image.vendor="AI Router"
LABEL org.opencontainers.image.licenses="MIT"
LABEL org.opencontainers.image.base.name="python:${PYTHON_VERSION}-slim"

# Create non-root user
RUN groupadd -r ai-router && \
    useradd -r -g ai-router -d /app -s /sbin/nologin ai-router

WORKDIR /app

# Copy only installed packages from builder
COPY --from=builder /root/.local /root/.local
ENV PATH=/root/.local/bin:$PATH

# Copy application code
COPY app/ ./app/

# Write build metadata for /version endpoint
RUN mkdir -p /app/.meta && \
    echo "{\"version\": \"${VERSION}\", \"build_date\": \"${BUILD_DATE:-unknown}\", \"git_commit\": \"${GIT_COMMIT:-unknown}\", \"python_version\": \"${PYTHON_VERSION}\"}" > /app/.meta/build.json

# Port and health check
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --retries=3 --start-period=10s \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

# Drop privileges
USER ai-router

CMD ["python", "-m", "app.main"]
