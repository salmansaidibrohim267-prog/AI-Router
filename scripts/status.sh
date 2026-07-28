#!/usr/bin/env bash
set -euo pipefail

# AI Router - Status Report Script
# Usage: ./scripts/status.sh

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
COMPOSE_FILE="${PROJECT_DIR}/docker-compose.yml"

echo "=========================================="
echo "  AI Router - Status Report"
echo "  $(date -u)"
echo "=========================================="

# 1. Docker containers
echo ""
echo "--- Docker Containers ---"
if [ -f "$COMPOSE_FILE" ]; then
  docker compose -f "$COMPOSE_FILE" ps 2>/dev/null || docker ps --filter network=ai-router-net --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
else
  docker ps --filter name=ai-router --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
fi

# 2. Resource usage
echo ""
echo "--- Resource Usage ---"
for container in ai-router prometheus grafana loki promtail; do
  if docker ps --format '{{.Names}}' | grep -q "^${container}$"; then
    stats=$(docker stats "$container" --no-stream --format "{{.Name}}: CPU {{.CPUPerc}}, MEM {{.MemUsage}}" 2>/dev/null)
    echo "  ${stats}"
  fi
done

# 3. API health
echo ""
echo "--- API Health ---"
HEALTH=$(curl -sf http://localhost:8000/health 2>/dev/null || echo "")
if [ -n "$HEALTH" ]; then
  VERSION=$(echo "$HEALTH" | python3 -c "import sys,json; print(json.load(sys.stdin).get('version','?'))" 2>/dev/null)
  STATUS=$(echo "$HEALTH" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('status','?')), print('  Healthy/Sick:', d.get('healthy_count',0),'/',d.get('total_providers',0))" 2>/dev/null)
  echo "  Version: ${VERSION}"
  echo "  Status: $(echo "$HEALTH" | python3 -c "import sys,json; print(json.load(sys.stdin).get('status','unknown'))" 2>/dev/null)"
  echo "  Providers: $(echo "$HEALTH" | python3 -c "import sys,json; d=json.load(sys.stdin); print(f\"{d.get('healthy_count',0)} healthy / {d.get('total_providers',0)} total\")" 2>/dev/null)"
else
  echo "  API not reachable"
fi

# 4. Uptime
echo ""
echo "--- Uptime ---"
if [ -n "$HEALTH" ]; then
  echo "  API: $(echo "$HEALTH" | python3 -c "import sys,json; print(json.load(sys.stdin).get('uptime_seconds','?') if 'uptime_seconds' in json.load(sys.stdin) else 'N/A')" 2>/dev/null)s"
fi
for container in ai-router prometheus grafana loki; do
  if docker ps --format '{{.Names}}' | grep -q "^${container}$"; then
    created=$(docker inspect "$container" --format '{{.Created}}' 2>/dev/null | cut -d. -f1 | tr 'T' ' ')
    echo "  ${container}: since ${created}"
  fi
done

# 5. Docker volumes
echo ""
echo "--- Volumes ---"
docker volume ls --filter name=ai-router --format "  {{.Name}}" 2>/dev/null || echo "  No ai-router volumes found"

# 6. Image info
echo ""
echo "--- Image ---"
docker images ai-router --format "  Tag: {{.Tag}}, Size: {{.Size}}, Created: {{.CreatedSince}}" 2>/dev/null || echo "  No local ai-router image"

echo ""
echo "=========================================="
