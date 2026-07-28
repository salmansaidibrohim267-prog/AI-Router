#!/usr/bin/env bash
set -euo pipefail

# AI Router - Production Prune Script
# Usage: ./scripts/prune.sh [--days 30] [--dry-run]

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
BACKUP_DIR="${PROJECT_DIR}/backups"
DAYS=30
DRY_RUN=false

while [[ $# -gt 0 ]]; do
  case "$1" in
    --days) DAYS="$2"; shift 2 ;;
    --dry-run) DRY_RUN=true; shift ;;
    *) echo "Unknown option: $1"; exit 1 ;;
  esac
done

echo "[prune] Pruning backups older than ${DAYS} days in ${BACKUP_DIR}"
if [ "$DRY_RUN" = true ]; then
  echo "[prune] DRY RUN - no files will be deleted"
fi

if [ ! -d "$BACKUP_DIR" ]; then
  echo "[prune] No backups directory found: ${BACKUP_DIR}"
  exit 0
fi

# Find and optionally delete old backups
find "$BACKUP_DIR" -maxdepth 1 -type d -name "????????_??????" | while read -r dir; do
  dirname=$(basename "$dir")
  dirdate="${dirname:0:8}"
  cutoff=$(date -d "-${DAYS} days" +%Y%m%d)

  if [[ "$dirdate" < "$cutoff" ]]; then
    size=$(du -sh "$dir" | cut -f1)
    if [ "$DRY_RUN" = true ]; then
      echo "[prune] Would delete: ${dir} (${size})"
    else
      echo "[prune] Deleting: ${dir} (${size})"
      rm -rf "$dir"
    fi
  fi
done

# Prune Docker resources (optional)
if [ "$DRY_RUN" = false ]; then
  echo "[prune] Pruning unused Docker resources..."
  docker system prune -f --volumes 2>/dev/null || true
fi

echo "[prune] Prune complete"
