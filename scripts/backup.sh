#!/usr/bin/env bash
set -euo pipefail

# AI Router - Production Backup Script
# Usage: ./scripts/backup.sh [output_dir]

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
OUTPUT_DIR="${1:-$PROJECT_DIR/backups}"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_DIR="${OUTPUT_DIR}/${TIMESTAMP}"
COMPOSE="${PROJECT_DIR}/docker-compose.yml"

mkdir -p "$BACKUP_DIR"

echo "[backup] Starting backup to ${BACKUP_DIR}"

# 1. Configuration
echo "[backup] Backing up configuration..."
tar czf "${BACKUP_DIR}/config.tar.gz" \
  -C "$PROJECT_DIR" \
  config/ \
  --exclude='.git' \
  --exclude='__pycache__'

# 2. Grafana dashboards & provisioning (provisioned configs, not DB)
echo "[backup] Backing up Grafana provisioning..."
if [ -d "${PROJECT_DIR}/grafana" ]; then
  tar czf "${BACKUP_DIR}/grafana-provisioning.tar.gz" \
    -C "$PROJECT_DIR" \
    grafana/dashboards/ \
    grafana/provisioning/
fi

# 3. Prometheus data volume
echo "[backup] Backing up Prometheus data..."
if docker ps --format '{{.Names}}' | grep -q '^prometheus$'; then
  docker run --rm \
    -v prometheus_data:/data \
    -v "${BACKUP_DIR}:/backup" \
    alpine tar czf /backup/prometheus-data.tar.gz -C /data .
  echo "[backup] Prometheus data backed up"
fi

# 4. Loki data volume
echo "[backup] Backing up Loki data..."
if docker ps --format '{{.Names}}' | grep -q '^loki$'; then
  docker run --rm \
    -v loki_data:/data \
    -v "${BACKUP_DIR}:/backup" \
    alpine tar czf /backup/loki-data.tar.gz -C /data .
  echo "[backup] Loki data backed up"
fi

# 5. Grafana data volume (DB, etc.)
echo "[backup] Backing up Grafana data..."
if docker ps --format '{{.Names}}' | grep -q '^grafana$'; then
  docker run --rm \
    -v grafana_data:/data \
    -v "${BACKUP_DIR}:/backup" \
    alpine tar czf /backup/grafana-data.tar.gz -C /data .
  echo "[backup] Grafana data backed up"
fi

# 6. Router logs
echo "[backup] Backing up router logs..."
if [ -d "${PROJECT_DIR}/logs" ]; then
  tar czf "${BACKUP_DIR}/logs.tar.gz" -C "$PROJECT_DIR" logs/
fi

# 7. Environment file (redact secrets)
echo "[backup] Backing up environment (secrets redacted)..."
if [ -f "${PROJECT_DIR}/.env" ]; then
  cp "${PROJECT_DIR}/.env" "${BACKUP_DIR}/.env.backup"
  # Create a redacted copy for logs
  sed 's/=.*/=REDACTED/' "${PROJECT_DIR}/.env" > "${BACKUP_DIR}/.env.redacted"
fi

# 8. Docker compose file
echo "[backup] Backing up docker-compose..."
cp "${COMPOSE}" "${BACKUP_DIR}/docker-compose.yml"

# 9. Backup manifest
cat > "${BACKUP_DIR}/manifest.txt" <<EOF
Backup Timestamp: ${TIMESTAMP}
Project: AI Router Gateway
Files:
  - config.tar.gz
  - grafana-provisioning.tar.gz (if exists)
  - prometheus-data.tar.gz (if exists)
  - loki-data.tar.gz (if exists)
  - grafana-data.tar.gz (if exists)
  - logs.tar.gz
  - .env.backup
  - docker-compose.yml
EOF

echo "[backup] Manifest written to ${BACKUP_DIR}/manifest.txt"

# Calculate total size
TOTAL_SIZE=$(du -sh "$BACKUP_DIR" | cut -f1)
echo "[backup] Backup complete: ${BACKUP_DIR} (${TOTAL_SIZE})"
echo "[backup] To restore: ./scripts/restore.sh ${BACKUP_DIR}"
