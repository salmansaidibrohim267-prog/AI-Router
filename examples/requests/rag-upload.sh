#!/usr/bin/env bash
# Ingest a sample document into the knowledge base.
set -euo pipefail

BASE="${BASE:-http://localhost:8000}"
KEY="${KEY:-test-key}"
DOC="${DOC:-../datasets/sample-knowledge.md}"

curl -s -X POST "$BASE/knowledge/documents/upload" \
  -H "Authorization: Bearer $KEY" \
  -F "file=@$DOC" | python3 -m json.tool
