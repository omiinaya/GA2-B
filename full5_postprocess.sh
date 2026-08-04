#!/bin/bash
# full5_postprocess.sh — repair + verdict extraction for the CURRENT full5
# resume run (started as raw `timeout` cmd, so the launcher's post-processing
# will NOT fire). Waits for the benchmark process to exit, repairs any
# contamination-damaged questions, extracts the official metrics, and writes
# /tmp/mem0bench_full5.out so the existing verdict watcher delivers them.
set -u

RESULT=/tmp/mem0bench_full5.out
LOGFILE=/tmp/mem0bench_full5_postprocess.log
RESULT_DIR=/tmp/mem0bench/full5/predicted_stmem-full5-zen
PROJ=stmem-full5-zen

log() { echo "$(date '+%H:%M:%S') $*" >> "$LOGFILE"; }

log "postprocessor started, waiting for benchmark exit..."

# Wait for the benchmark process to fully exit (same pattern the chain uses).
while ps aux | grep -E "stmem-full5-zen|benchmarks.locomo.run" | grep -v grep > /dev/null 2>&1; do
    sleep 60
done
log "benchmark exited; starting repair+extraction"

# Give STDB a moment to settle, then check for contamination.
sleep 30

if [ ! -d "$RESULT_DIR" ]; then
    log "FATAL: result dir missing: $RESULT_DIR"
    exit 1
fi

CONTAM_COUNT=$(grep -l '"total_results": 0' "$RESULT_DIR"/conv*_q*.json 2>/dev/null | wc -l)
log "contaminated questions found: $CONTAM_COUNT"

if [ "$CONTAM_COUNT" -gt 0 ]; then
    log "running repair script..."
    /home/hindsight/spacetime-memory/.venv/bin/python3 \
        /home/hindsight/spacetime-memory/scripts/repair_locomo_contamination.py \
        --results-dir "$RESULT_DIR" \
        --dataset /home/hindsight/spacetime-memory/data/locomo10.json \
        --project-name "$PROJ" \
        --db spacetime-memory-v2 --stmem-host 192.168.1.10 --stmem-port 3001 \
        --run-id a2e9b6fd \
        --answerer-model deepseek-v4-flash-free --judge-model deepseek-v4-flash-free \
        --cutoff 10 20 50 200 \
        >> "$LOGFILE" 2>&1
    log "repair finished"
else
    log "no contamination, skipping repair"
fi

# Extract the official metrics from the newest results file (repaired or not).
NEW=$(ls -t /tmp/mem0bench/full5/locomo_results_*.json 2>/dev/null | head -1)
log "newest results file: ${NEW:-NONE}"

if [ -z "$NEW" ]; then
    log "FATAL: no locomo_results_*.json found; verdict cannot be extracted"
    exit 1
fi

/home/hindsight/spacetime-memory/.venv/bin/python3 - "$NEW" > "$RESULT" <<'PY'
import json, sys
d = json.load(open(sys.argv[1]))
print("FULL OFFICIAL MEM0 LoCoMo RUN (date-anchored + per-project identity, OpenCode Zen deepseek)")
md = d.get("metadata", {})
print("answerer_model:", md.get("answerer_model"))
print("total_questions:", md.get("total_questions"))
if md.get("repair_note"):
    print("repair_note:", md.get("repair_note"))
for cutoff, m in d.get("metrics_by_cutoff", {}).items():
    o = m.get("overall", {})
    print(f"{cutoff}: {o.get('accuracy',0):.2f}% ({o.get('correct')}/{o.get('total')})")
print("MEM0_PUBLISHED=91.56")
PY

log "verdict written to $RESULT"
cat "$RESULT" >> "$LOGFILE"
