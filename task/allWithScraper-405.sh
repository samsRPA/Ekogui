#!/usr/bin/env bash
set -euo pipefail

curl -X POST "http://127.0.0.1:8000/api/v1/ekogui/allWithScraper" \
  -H "Content-Type: application/json" \
  -d '{
    "entidades": [405],
    "estado": "PROCESO_ENTIDAD_ACTIVO",
    "batchSize": 10
  }'
