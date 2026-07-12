#!/bin/bash

# Move to project root. This works because this file is inside the scripts folder.
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT" || exit 1

# Create log folder if it does not exist.
mkdir -p logs

{
  echo "============================================================"
  echo "Service Sonar daily refresh started at $(date)"
  echo "============================================================"

  # Run scheduled pipeline refresh:
  # --scrape    = collect new forum posts
  # --innovate  = update Agent 4 service opportunities after analysis
  # --agent3-limit 50 = limit LLM processing per run to avoid API overload
  # Trend snapshots, proactive alerts and evaluation reports run by default.
  python3 pipeline_refresh.py --scrape --innovate --agent3-limit 50 --agent3-sleep 1

  echo "============================================================"
  echo "Service Sonar daily refresh finished at $(date)"
  echo "============================================================"
  echo ""
} >> logs/daily_refresh.log 2>&1
