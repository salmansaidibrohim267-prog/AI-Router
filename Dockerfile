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
LABEL org.opencontainers.image.url="https://github.com/salmansaidibrohim267-prog/AI-Router"
LABEL org.opencontainers.image.source="https://github.com/salmansaidibrohim267-prog/AI-Router"
LABEL org.opencontainers.image.documentation="https://github.com/salmansaidibrohim267-prog/AI-Router#readme"
LABEL org.opencontainers.image.vendor="AI Router"
LABEL org.opencontainers.image.licenses="MIT"
LABEL org.opencontainers.image.authors="salmansaidibrohim267-prog"
LABEL org.opencontainers.image.base.name="python:${PYTHON_VERSION}-slim"

# Create non-root user
RUN groupadd -r ai-router && \
    useradd -r -g ai-router -d /app -s /sbin/nologin ai-router

WORKDIR /app

# Copy installed packages into the global site-packages so the non-root
# runtime user (ai-router) can import them (/root/.local is mode 700)
COPY --from=builder /root/.local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages/
COPY --from=builder /root/.local/bin /usr/local/bin/

# Copy application code
COPY app/ ./app/
COPY config/ ./config/

# Write build metadata for /version endpoint (read from app/.meta at runtime)
RUN mkdir -p /app/app/.meta && \
    echo "{\"version\": \"${VERSION}\", \"build_date\": \"${BUILD_DATE:-unknown}\", \"git_commit\": \"${GIT_COMMIT:-unknown}\", \"python_version\": \"${PYTHON_VERSION}\"}" > /app/app/.meta/build.json && \
    chown -R ai-router:ai-router /app/app/.meta

# Make runtime-writable paths belong to the app user
RUN mkdir -p /app/logs && chown -R ai-router:ai-router /app/logs

# Port and health check
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --retries=3 --start-period=10s \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

# Drop privileges
USER ai-router

STOPSIGNAL SIGTERM

CMD ["python", "-m", "app.main"]
