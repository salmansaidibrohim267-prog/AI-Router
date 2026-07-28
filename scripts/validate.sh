#!/usr/bin/env bash
set -euo pipefail

# AI Router - Configuration & Dependency Validation Script
# Usage: ./scripts/validate.sh

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
FAILED=0

echo "=========================================="
echo "  AI Router - Validation"
echo "=========================================="

# 1. Check required files
echo ""
echo "[1/9] Required files..."
REQUIRED_FILES=(
  "${PROJECT_DIR}/Dockerfile"
  "${PROJECT_DIR}/docker-compose.yml"
  "${PROJECT_DIR}/requirements.txt"
  "${PROJECT_DIR}/app/__init__.py"
  "${PROJECT_DIR}/app/api.py"
  "${PROJECT_DIR}/app/main.py"
  "${PROJECT_DIR}/app/config.py"
)
for f in "${REQUIRED_FILES[@]}"; do
  if [ -f "$f" ]; then
    echo "  PASS: $(basename "$f")"
  else
    echo "  FAIL: $f not found"
    FAILED=1
  fi
done

# 2. Check config files
echo ""
echo "[2/9] Configuration files..."
if [ -f "${PROJECT_DIR}/config/models.yaml" ]; then
  echo "  PASS: config/models.yaml"
  # Basic YAML validation
  python3 -c "import yaml; yaml.safe_load(open('${PROJECT_DIR}/config/models.yaml'))" 2>/dev/null && \
    echo "  PASS: models.yaml is valid YAML" || \
    echo "  FAIL: models.yaml has invalid YAML"
else
  echo "  FAIL: config/models.yaml not found"
  FAILED=1
fi

# 3. Validate docker-compose
echo ""
echo "[3/9] Docker Compose..."
if command -v docker &>/dev/null; then
  docker compose -f "${PROJECT_DIR}/docker-compose.yml" config > /dev/null 2>&1 && \
    echo "  PASS: docker-compose.yml is valid" || \
    echo "  FAIL: docker-compose.yml is invalid"
fi

# 4. Check Dockerfile syntax
echo ""
echo "[4/9] Dockerfile..."
if command -v docker &>/dev/null; then
  docker build -f "$PROJECT_DIR/Dockerfile" --check "$PROJECT_DIR" > /dev/null 2>&1 && \
    echo "  PASS: Dockerfile syntax valid" || \
    echo "  WARN: Docker build check not supported on this version"
fi

# 5. Check for .env file
echo ""
echo "[5/9] Environment file..."
if [ -f "${PROJECT_DIR}/.env" ]; then
  echo "  PASS: .env file exists"
  # Warn about empty keys
  while IFS='=' read -r key value; do
    if [[ -n "$key" && -z "$value" && ! "$key" =~ ^# ]]; then
      echo "  WARN: ${key} is empty"
    fi
  done < "${PROJECT_DIR}/.env"
else
  echo "  WARN: No .env file (secrets may be provided via Docker Secrets)"
fi

# 6. Check Python dependencies
echo ""
echo "[6/9] Python dependencies..."
if command -v python3 &>/dev/null; then
  python3 -c "
try:
    import fastapi, uvicorn, pydantic, httpx, yaml, prometheus_client
    print('  PASS: All core dependencies available')
except ImportError as e:
    print(f'  FAIL: Missing dependency: {e}')
" 2>/dev/null || echo "  WARN: Could not check Python dependencies"
fi

# 7. Check ports availability
echo ""
echo "[7/9] Port availability..."
for port in 8000 9090 3000 3100; do
  if ss -tlnp "sport = :${port}" 2>/dev/null | grep -q ":$port"; then
    echo "  INUSE: Port ${port} is already in use"
  else
    echo "  FREE:  Port ${port} is available"
  fi
done

# 8. Check Docker resources
echo ""
echo "[8/9] Docker resources..."
AVAILABLE_MEM=$(docker info --format '{{.MemTotal}}' 2>/dev/null | numfmt --to=iec || echo "unknown")
echo "  Total memory: ${AVAILABLE_MEM}"
RUNNING=$(docker ps -q 2>/dev/null | wc -l)
echo "  Running containers: ${RUNNING}"

# 9. Check git status
echo ""
echo "[9/9] Git status..."
if git -C "$PROJECT_DIR" rev-parse --git-dir > /dev/null 2>&1; then
  BRANCH=$(git -C "$PROJECT_DIR" rev-parse --abbrev-ref HEAD)
  COMMIT=$(git -C "$PROJECT_DIR" rev-parse --short HEAD)
  echo "  Branch: ${BRANCH}"
  echo "  Commit: ${COMMIT}"
  if [ -n "$(git -C "$PROJECT_DIR" status --porcelain)" ]; then
    echo "  WARN: Uncommitted changes detected"
  else
    echo "  PASS: Working tree is clean"
  fi
else
  echo "  WARN: Not a git repository"
fi

echo ""
echo "=========================================="
if [ $FAILED -eq 0 ]; then
  echo "  ALL CHECKS PASSED"
else
  echo "  SOME CHECKS FAILED - review messages above"
fi
echo "=========================================="
exit $FAILED
