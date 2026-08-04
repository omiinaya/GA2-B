#!/bin/bash
# Full official Mem0 LoCoMo harness run against Spacetime-Memory with:
#   - date-anchored content (session dates embedded in searchable text)
#   - per-project STDB identity (no shared-account auth clobbering)
#   - ALL LLM via our OpenCode Zen chain (:4004 -> :4002, x-api-key: public)
# No OpenRouter (cardinal rule #2). Gateway-immune via no_agent cron.
set -e

RESULT=/tmp/mem0bench_full5.out
LOGFILE=/tmp/mem0bench_full5.log

echo "Starting official Mem0 harness full run at $(date)" > "$LOGFILE"

cd /home/hindsight/mem0/evaluation

rm -rf /tmp/mem0bench/full5
timeout 90000 env \
    OTEL_ENABLED=false \
    LLM_BASE_URL=http://localhost:4004/v1 \
    OPENAI_API_KEY=dummy-key \
    PYTHONUNBUFFERED=1 \
    /home/hindsight/spacetime-memory/.venv/bin/python -m benchmarks.locomo.run \
        --project-name stmem-full5-zen \
        --backend stmem \
        --stmem-db spacetime-memory-v2 \
        --stmem-host 192.168.1.10 --stmem-port 3001 \
        --answerer-model deepseek-v4-flash-free \
        --judge-model deepseek-v4-flash-free \
        --conversations 0,1,2,3,4,5,6,7,8,9 \
        --top-k 200 \
        --max-workers 4 \
        --dataset-path /home/hindsight/spacetime-memory/data/locomo10.json \
        --output-dir /tmp/mem0bench/full5 \
        --max-questions 1540 \
    >> "$LOGFILE" 2>&1

rc=$?
echo "exit=$rc" > "$RESULT"

# ── REPAIR contamination (STDB restart outage on 2026-08-03) ──────────────
# If STDB was down during question scoring, search returned [] and those
# questions were judged against empty context (retrieval.total_results == 0).
# Re-search + re-answer + re-judge exactly those against the now-healthy DB so
# the extracted metrics are apples-to-apples, not penalized by infra.
RESULT_DIR=/tmp/mem0bench/full5/predicted_stmem-full5-zen
echo "Checking for contamination-damaged questions..." >> "$LOGFILE"
if [ -d "$RESULT_DIR" ]; then
    CONTAM_COUNT=$(grep -l '"total_results": 0' "$RESULT_DIR"/conv*_q*.json 2>/dev/null | wc -l)
    if [ "$CONTAM_COUNT" -gt 0 ]; then
        echo "Repairing $CONTAM_COUNT contaminated questions (STDB outage) ..." >> "$LOGFILE"
        /home/hindsight/spacetime-memory/.venv/bin/python3 \
            /home/hindsight/spacetime-memory/scripts/repair_locomo_contamination.py \
            --results-dir "$RESULT_DIR" \
            --dataset /home/hindsight/spacetime-memory/data/locomo10.json \
            --project-name stmem-full5-zen \
            --db spacetime-memory-v2 --stmem-host 192.168.1.10 --stmem-port 3001 \
            --run-id a2e9b6fd \
            --answerer-model deepseek-v4-flash-free --judge-model deepseek-v4-flash-free \
            --cutoff 10 20 50 200 \
            >> "$LOGFILE" 2>&1
        echo "Repair finished $(date)" >> "$LOGFILE"
    else
        echo "No contaminated questions found." >> "$LOGFILE"
    fi
fi

# Extract the official metrics from the newest results file.
NEW=$(ls -t /tmp/mem0bench/full5/locomo_results_*.json 2>/dev/null | head -1)
if [ -n "$NEW" ]; then
    /home/hindsight/spacetime-memory/.venv/bin/python3 - "$NEW" > "$RESULT" <<'PY'
import json, sys
d = json.load(open(sys.argv[1]))
print("FULL OFFICIAL MEM0 LoCoMo RUN (date-anchored + per-project identity, OpenCode Zen deepseek)")
md = d.get("metadata", {})
print("answerer_model:", md.get("answerer_model"))
print("total_questions:", md.get("total_questions"))
for cutoff, m in d.get("metrics_by_cutoff", {}).items():
    o = m.get("overall", {})
    print(f"{cutoff}: {o.get('accuracy',0):.2f}% ({o.get('correct')}/{o.get('total')})")
print("MEM0_PUBLISHED=91.56")
PY
fi