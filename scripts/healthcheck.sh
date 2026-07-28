#!/usr/bin/env bash
set -euo pipefail

# AI Router - Health Check Script
# Usage: ./scripts/healthcheck.sh [--wait]
#   --wait: Poll until healthy (useful in CI/deploy)

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
WAIT=false
MAX_ATTEMPTS=30
INTERVAL=2

if [[ "${1:-}" == "--wait" ]]; then
  WAIT=true
fi

check_health() {
  local url="${1:-http://localhost:8000/health}"
  local response
  response=$(curl -sf "$url" 2>&1) || return 1
  local status
  status=$(echo "$response" | python3 -c "import sys,json; print(json.load(sys.stdin).get('status','unknown'))" 2>/dev/null)
  if [ "$status" = "ok" ]; then
    return 0
  elif [ "$status" = "degraded" ]; then
    echo "[healthcheck] WARNING: Service is degraded (all providers may be down)"
    return 0
  fi
  return 1
}

if [ "$WAIT" = true ]; then
  echo "[healthcheck] Waiting for AI Router to become healthy..."
  for i in $(seq 1 $MAX_ATTEMPTS); do
    if check_health "http://localhost:8000/health"; then
      echo "[healthcheck] AI Router is healthy after ${i}s"
      # Print full health summary
      curl -s http://localhost:8000/health | python3 -m json.tool
      exit 0
    fi
    sleep "$INTERVAL"
  done
  echo "[healthcheck] FAILED: AI Router did not become healthy after ${MAX_ATTEMPTS}s"
  exit 1
fi

# Single check with verbose output
echo "[healthcheck] Checking AI Router health..."
if check_health "http://localhost:8000/health"; then
  echo "[healthcheck] PASS: AI Router is healthy"
else
  echo "[healthcheck] FAIL: AI Router health check failed"
  # Show container status
  docker ps --filter name=ai-router --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}" 2>/dev/null || true
  exit 1
fi

# Check all containers if compose file exists
COMPOSE_FILE="${PROJECT_DIR}/docker-compose.yml"
if [ -f "$COMPOSE_FILE" ]; then
  echo ""
  echo "[healthcheck] All service statuses:"
  for service in ai-router prometheus grafana loki promtail; do
    if docker ps --format '{{.Names}}' | grep -q "^${service}$"; then
      status=$(docker inspect "$service" --format '{{.State.Health.Status}}' 2>/dev/null || echo "unknown")
      echo "  ${service}: running (health: ${status})"
    fi
  done
fi
