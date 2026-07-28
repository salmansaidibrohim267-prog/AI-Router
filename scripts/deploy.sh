#!/usr/bin/env bash
set -euo pipefail

# AI Router - Production Deploy Script
# Usage: ./scripts/deploy.sh [--profile production] [--tag latest]

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
PROFILE="${1:-production}"
TAG="${2:-latest}"
COMPOSE_FILE="${PROJECT_DIR}/docker-compose.yml"

echo "[deploy] Starting deployment (profile=${PROFILE}, tag=${TAG})"

# 1. Validate configuration
echo "[deploy] Step 1/6: Validating configuration..."
python3 -c "
from app.config import config_manager
cfg = config_manager.config
if cfg:
    print(f'  Config loaded: {len(cfg.tasks)} tasks, hash={config_manager.config_hash}')
else:
    print('  WARNING: No configuration loaded')
" 2>/dev/null || echo "  WARNING: Could not validate config (dependencies may not be installed)"

# 2. Validate docker-compose
echo "[deploy] Step 2/6: Validating docker-compose..."
docker compose -f "$COMPOSE_FILE" config > /dev/null
echo "  docker-compose validation passed"

# 3. Build Docker image
echo "[deploy] Step 3/6: Building Docker image..."
GIT_COMMIT=$(git rev-parse --short HEAD 2>/dev/null || echo "unknown")
BUILD_DATE=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
docker build \
  --build-arg VERSION="${TAG}" \
  --build-arg BUILD_DATE="${BUILD_DATE}" \
  --build-arg GIT_COMMIT="${GIT_COMMIT}" \
  -t "ai-router:${TAG}" \
  -f "$PROJECT_DIR/Dockerfile" \
  "$PROJECT_DIR"
echo "  Image built: ai-router:${TAG}"

# 4. Check health before deploy
echo "[deploy] Step 4/6: Checking pre-deploy health..."
if curl -sf http://localhost:8000/health > /dev/null 2>&1; then
  echo "  Current instance is healthy"
else
  echo "  No running instance detected (fresh deploy)"
fi

# 5. Deploy with profile
echo "[deploy] Step 5/6: Deploying services (profile=${PROFILE})..."
docker compose -f "$COMPOSE_FILE" --profile "${PROFILE}" up -d --no-deps --build ai-router
echo "  ai-router service updated"

# 6. Wait for health
echo "[deploy] Step 6/6: Waiting for health check..."
MAX_ATTEMPTS=30
for i in $(seq 1 $MAX_ATTEMPTS); do
  if curl -sf http://localhost:8000/health > /dev/null 2>&1; then
    STATUS=$(curl -s http://localhost:8000/health | python3 -c "import sys,json; print(json.load(sys.stdin).get('status','unknown'))" 2>/dev/null)
    echo "  Health check passed (status=${STATUS}) after ${i}s"
    echo "[deploy] Deployment complete!"
    exit 0
  fi
  sleep 2
done

echo "[deploy] FAILED: Health check did not pass within ${MAX_ATTEMPTS}s"
echo "[deploy] Check logs: docker-compose logs ai-router"
exit 1
