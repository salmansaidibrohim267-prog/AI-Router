#!/usr/bin/env bash
set -euo pipefail

# AI Router - Deployment Verification Script
# Usage: ./scripts/verify.sh

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
FAILED=0

echo "=========================================="
echo "  AI Router - Deployment Verification"
echo "=========================================="

# 1. Basic connectivity
echo ""
echo "[1/8] Checking API connectivity..."
if curl -sf http://localhost:8000/ > /dev/null 2>&1; then
  echo "  PASS: API is reachable"
else
  echo "  FAIL: Cannot reach API on localhost:8000"
  echo "  Is the service running? Try: docker-compose ps"
  FAILED=1
fi

# 2. Health endpoint
echo ""
echo "[2/8] Checking health endpoint..."
HEALTH=$(curl -sf http://localhost:8000/health 2>/dev/null || echo "")
if [ -n "$HEALTH" ]; then
  STATUS=$(echo "$HEALTH" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('status','unknown'))" 2>/dev/null)
  echo "  PASS: Health endpoint returns status=${STATUS}"
  echo "$HEALTH" | python3 -m json.tool 2>/dev/null | head -20
else
  echo "  FAIL: Health endpoint not responding"
  FAILED=1
fi

# 3. Configuration loaded
echo ""
echo "[3/8] Checking configuration..."
CONFIG=$(curl -sf http://localhost:8000/config 2>/dev/null || echo "")
if [ -n "$CONFIG" ] && echo "$CONFIG" | python3 -c "import sys,json; d=json.load(sys.stdin); assert len(d.get('tasks',[])) > 0" 2>/dev/null; then
  echo "  PASS: Configuration loaded with tasks"
else
  echo "  FAIL: Configuration not properly loaded"
  FAILED=1
fi

# 4. Metrics endpoint
echo ""
echo "[4/8] Checking Prometheus metrics..."
METRICS=$(curl -sf http://localhost:8000/metrics 2>/dev/null || echo "")
if echo "$METRICS" | grep -q "ai_router_uptime_seconds"; then
  echo "  PASS: Metrics endpoint returns prometheus data"
else
  echo "  FAIL: Metrics endpoint not returning expected data"
  FAILED=1
fi

# 5. Docker containers
echo ""
echo "[5/8] Checking Docker container status..."
COMPOSE_FILE="${PROJECT_DIR}/docker-compose.yml"
if [ -f "$COMPOSE_FILE" ]; then
  RUNNING=$(docker ps --format '{{.Names}}' | sort)
  echo "  Running containers:"
  echo "$RUNNING" | sed 's/^/    /'
  # Check ai-router specifically
  if echo "$RUNNING" | grep -q "^ai-router$"; then
    HEALTH_STATE=$(docker inspect ai-router --format '{{.State.Health.Status}}' 2>/dev/null || echo "unknown")
    echo "  ai-router health: ${HEALTH_STATE}"
  fi
else
  echo "  SKIP: No docker-compose.yml found"
fi

# 6. Configuration files
echo ""
echo "[6/8] Checking configuration files..."
CONFIG_DIR="${PROJECT_DIR}/config"
if [ -f "${CONFIG_DIR}/models.yaml" ]; then
  echo "  PASS: config/models.yaml exists"
else
  echo "  FAIL: config/models.yaml not found"
  FAILED=1
fi
if [ -f "${PROJECT_DIR}/.env" ]; then
  echo "  PASS: .env file exists"
else
  echo "  WARN: .env file not found (secrets may be provided via other means)"
fi

# 7. Logs directory
echo ""
echo "[7/8] Checking logs..."
if [ -d "${PROJECT_DIR}/logs" ]; then
  LOG_FILES=$(ls -1 "${PROJECT_DIR}/logs/" 2>/dev/null | wc -l)
  echo "  PASS: Logs directory exists (${LOG_FILES} files)"
else
  echo "  WARN: Logs directory does not exist"
fi

# 8. Version endpoint
echo ""
echo "[8/8] Checking version info..."
VERSION=$(curl -sf http://localhost:8000/version 2>/dev/null || echo "")
if [ -n "$VERSION" ]; then
  echo "  PASS: Version endpoint responds"
  echo "$VERSION" | python3 -m json.tool 2>/dev/null
else
  echo "  WARN: /version endpoint not available (non-critical)"
fi

echo ""
echo "=========================================="
if [ $FAILED -eq 0 ]; then
  echo "  VERIFICATION PASSED"
else
  echo "  VERIFICATION FAILED - check messages above"
fi
echo "=========================================="
exit $FAILED
