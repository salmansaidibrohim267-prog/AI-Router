#!/usr/bin/env bash
set -euo pipefail

# AI Router - Production Rollback Script
# Usage: ./scripts/rollback.sh [tag]

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
TAG="${1:-previous}"
COMPOSE_FILE="${PROJECT_DIR}/docker-compose.yml"

echo "[rollback] Starting rollback to tag: ${TAG}"

# 1. Check if previous tag exists
echo "[rollback] Step 1/3: Checking image..."
if docker image inspect "ai-router:${TAG}" > /dev/null 2>&1; then
  echo "  Found image: ai-router:${TAG}"
else
  echo "  ERROR: Image 'ai-router:${TAG}' not found"
  echo "  Available tags:"
  docker images ai-router --format "  {{.Tag}}" | head -10
  exit 1
fi

# 2. Tag current as previous-timestamp (preserve current state)
CURRENT_HASH=$(docker inspect ai-router:latest --format '{{.Id}}' 2>/dev/null | cut -d: -f2 | cut -c1-12 || echo "unknown")
ROLLBACK_TIME=$(date +%Y%m%d_%H%M%S)
echo "[rollback] Step 2/3: Saving current image as ai-router:pre-${ROLLBACK_TIME}"
docker tag "ai-router:latest" "ai-router:pre-${ROLLBACK_TIME}"
echo "  Saved as ai-router:pre-${ROLLBACK_TIME} (${CURRENT_HASH})"

# 3. Deploy rollback tag
echo "[rollback] Step 3/3: Deploying rollback image..."
docker tag "ai-router:${TAG}" "ai-router:latest"

# For docker compose profiles, restart the service
if [ -f "$COMPOSE_FILE" ]; then
  docker compose -f "$COMPOSE_FILE" up -d --no-deps ai-router
else
  echo "  No docker-compose.yml found, restarting standalone container..."
  docker stop ai-router 2>/dev/null || true
  docker rm ai-router 2>/dev/null || true
  docker run -d --name ai-router -p 8000:8000 --env-file .env ai-router:latest
fi

echo "[rollback] Waiting for health check..."
for i in $(seq 1 15); do
  if curl -sf http://localhost:8000/health > /dev/null 2>&1; then
    STATUS=$(curl -s http://localhost:8000/health | python3 -c "import sys,json; print(json.load(sys.stdin).get('status','unknown'))" 2>/dev/null)
    echo "[rollback] Rollback complete! (status=${STATUS})"
    echo "[rollback] To revert further: ./scripts/rollback.sh pre-${ROLLBACK_TIME}"
    exit 0
  fi
  sleep 2
done

echo "[rollback] WARNING: Health check did not pass after rollback"
echo "[rollback] Check logs: docker-compose logs ai-router"
exit 1
