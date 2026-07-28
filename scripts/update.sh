#!/usr/bin/env bash
set -euo pipefail

# AI Router - Production Update Script
# Pulls latest base images, rebuilds ai-router, restarts stack
# Usage: ./scripts/update.sh [profile]

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
PROFILE="${1:-production}"
COMPOSE_FILE="${PROJECT_DIR}/docker-compose.yml"

echo "[update] Starting stack update (profile=${PROFILE})"

# 1. Git pull
echo "[update] Step 1/5: Pulling latest code..."
cd "$PROJECT_DIR"
git pull 2>/dev/null || echo "  Not a git repository or git not available, skipping"

# 2. Pull latest base images
echo "[update] Step 2/5: Pulling base images..."
docker compose -f "$COMPOSE_FILE" --profile "${PROFILE}" pull --ignore-pull-failures 2>/dev/null || \
  echo "  Some images could not be pulled (may be local builds)"

# 3. Build ai-router
echo "[update] Step 3/5: Building ai-router..."
GIT_COMMIT=$(git rev-parse --short HEAD 2>/dev/null || echo "unknown")
BUILD_DATE=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
docker build \
  --build-arg VERSION="2.0.0" \
  --build-arg BUILD_DATE="${BUILD_DATE}" \
  --build-arg GIT_COMMIT="${GIT_COMMIT}" \
  -t ai-router:latest \
  -f "$PROJECT_DIR/Dockerfile" \
  "$PROJECT_DIR"

# 4. Deploy
echo "[update] Step 4/5: Deploying updated stack..."
docker compose -f "$COMPOSE_FILE" --profile "${PROFILE}" up -d

# 5. Verify
echo "[update] Step 5/5: Verifying deployment..."
"${SCRIPT_DIR}/healthcheck.sh" --wait || {
  echo "[update] FAILED: Health check did not pass"
  exit 1
}

echo "[update] Update complete!"
