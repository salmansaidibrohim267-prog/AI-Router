#!/usr/bin/env bash
set -euo pipefail

# AI Router - Production Restore Script
# Usage: ./scripts/restore.sh <backup_dir>

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

if [ $# -lt 1 ]; then
  echo "Usage: $0 <backup_dir>"
  echo "Example: $0 backups/20250101_120000"
  exit 1
fi

BACKUP_DIR="$1"

if [ ! -d "$BACKUP_DIR" ]; then
  echo "[restore] ERROR: Backup directory not found: ${BACKUP_DIR}"
  exit 1
fi

echo "[restore] Starting restore from ${BACKUP_DIR}"

# Check if services are running and warn
if docker ps --format '{{.Names}}' | grep -q '^ai-router$'; then
  echo "[restore] WARNING: AI Router is currently running. Restoring may cause disruption."
  echo "[restore] Press ENTER to continue or Ctrl+C to abort..."
  read -r
fi

# 1. Restore configuration
if [ -f "${BACKUP_DIR}/config.tar.gz" ]; then
  echo "[restore] Restoring configuration..."
  tar xzf "${BACKUP_DIR}/config.tar.gz" -C "$PROJECT_DIR"
fi

# 2. Restore Grafana provisioning
if [ -f "${BACKUP_DIR}/grafana-provisioning.tar.gz" ]; then
  echo "[restore] Restoring Grafana provisioning..."
  tar xzf "${BACKUP_DIR}/grafana-provisioning.tar.gz" -C "$PROJECT_DIR"
fi

# 3. Restore Prometheus data
if [ -f "${BACKUP_DIR}/prometheus-data.tar.gz" ]; then
  echo "[restore] Restoring Prometheus data..."
  docker run --rm \
    -v prometheus_data:/data \
    -v "${BACKUP_DIR}:/backup" \
    alpine tar xzf /backup/prometheus-data.tar.gz -C /data
  echo "[restore] Prometheus data restored (will be available after container restart)"
fi

# 4. Restore Loki data
if [ -f "${BACKUP_DIR}/loki-data.tar.gz" ]; then
  echo "[restore] Restoring Loki data..."
  docker run --rm \
    -v loki_data:/data \
    -v "${BACKUP_DIR}:/backup" \
    alpine tar xzf /backup/loki-data.tar.gz -C /data
  echo "[restore] Loki data restored (will be available after container restart)"
fi

# 5. Restore Grafana data
if [ -f "${BACKUP_DIR}/grafana-data.tar.gz" ]; then
  echo "[restore] Restoring Grafana data..."
  docker run --rm \
    -v grafana_data:/data \
    -v "${BACKUP_DIR}:/backup" \
    alpine tar xzf /backup/grafana-data.tar.gz -C /data
  echo "[restore] Grafana data restored (will be available after container restart)"
fi

# 6. Restore logs
if [ -f "${BACKUP_DIR}/logs.tar.gz" ]; then
  echo "[restore] Restoring logs..."
  tar xzf "${BACKUP_DIR}/logs.tar.gz" -C "$PROJECT_DIR"
fi

# 7. Restore environment file (optional)
if [ -f "${BACKUP_DIR}/.env.backup" ] && [ ! -f "${PROJECT_DIR}/.env" ]; then
  echo "[restore] Restoring .env file..."
  cp "${BACKUP_DIR}/.env.backup" "${PROJECT_DIR}/.env"
  echo "[restore] WARNING: .env file restored. Verify secrets are current."
fi

echo "[restore] Restore complete. Restart services with: docker-compose down && docker-compose up -d"
