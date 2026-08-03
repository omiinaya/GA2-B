#!/bin/bash
# SEQUENTIAL OFFICIAL-HARNESS CHAIN for Spacetime-Memory.
# Runs after the Mem0 LoCoMo full (stmem-full-zen-dated) finishes.
# Order: Zep LoCoMo -> Mem0 LongMemEval -> Mem0 BEAM.
# All LLM via our OpenCode Zen chain (:4004 -> :4002, x-api-key: public).
# No OpenRouter (cardinal rule #2). Gateway-immune via no_agent cron.
set -e

MASTER=/tmp/official_chain.out
LOGFILE=/tmp/official_chain.log
echo "Chain start $(date)" > "$LOGFILE"

# Wait for Mem0 LoCoMo full run (full5) to finish first
echo "Waiting for Mem0 LoCoMo official run..." >> "$LOGFILE"
while ps aux | grep -E "stmem-full5-zen|benchmarks.locomo.run" | grep -v grep > /dev/null 2>&1; do
    sleep 120
done
echo "Mem0 LoCoMo done at $(date)" >> "$LOGFILE"

# ── 1. ZEP OFFICIAL LOCOMO ──────────────────────────────────────────────
echo "=== ZEP OFFICIAL LOCOMO ($(date)) ===" >> "$LOGFILE"
cd /home/hindsight/zep/benchmarks/locomo
PREFIX="stmem-chain"
rm -f /tmp/zep_harness_identity.token
timeout 10800 env \
    OTEL_ENABLED=false \
    OPENAI_API_KEY=dummy-key OPENAI_BASE_URL=http://localhost:4004/v1 \
    ZEP_API_KEY=dummy STDB_DB=spacetime-memory-v2 \
    /home/hindsight/spacetime-memory/.venv/bin/python -m benchmark \
        --ingest --config benchmark_config_stmem.yaml --prefix "$PREFIX" \
    >> "$LOGFILE" 2>&1
echo "Zep ingest done $(date)" >> "$LOGFILE"
timeout 10800 env \
    OTEL_ENABLED=false \
    OPENAI_API_KEY=dummy-key OPENAI_BASE_URL=http://localhost:4004/v1 \
    ZEP_API_KEY=dummy STDB_DB=spacetime-memory-v2 \
    /home/hindsight/spacetime-memory/.venv/bin/python -m benchmark \
        --eval --config benchmark_config_stmem.yaml --prefix "$PREFIX" --num-runs 1 \
    >> "$LOGFILE" 2>&1
echo "Zep eval done $(date)" >> "$LOGFILE"
NEWEST=$(ls -t /home/hindsight/zep/benchmarks/locomo/experiments/experiment_*/experiment_summary.json 2>/dev/null | head -1)
echo "ZEP_RESULT_FILE=$NEWEST" >> "$MASTER"
if [ -n "$NEWEST" ]; then
    /home/hindsight/spacetime-memory/.venv/bin/python3 - "$NEWEST" >> "$MASTER" <<'PY'
import json, sys
d = json.load(open(sys.argv[1]))
am = d.get("aggregated_metrics", {})
acc = am.get("accuracy", {})
print("ZEP OFFICIAL LOCOMO (Zep harness, our Zen chain adapter)")
print(f"  accuracy.mean: {acc.get('mean', 0)*100:.2f}%  (median {acc.get('median', 0)*100:.2f}%)")
print(f"  config: {d.get('config', {}).get('models', {}).get('response_model')}")
print("ZEP_PUBLISHED_LOCOMO=69.6 (gpt-4o-mini)")
PY
fi

# ── 2. MEM0 OFFICIAL LONGMEMEVAL ────────────────────────────────────────
echo "=== MEM0 OFFICIAL LONGMEMEVAL ($(date)) ===" >> "$LOGFILE"
cd /home/hindsight/mem0/evaluation
timeout 28800 env \
    OTEL_ENABLED=false \
    LLM_BASE_URL=http://localhost:4004/v1 OPENAI_API_KEY=dummy-key \
    PYTHONUNBUFFERED=1 \
    /home/hindsight/spacetime-memory/.venv/bin/python -m benchmarks.longmemeval.run \
        --project-name stmem-chain-lme \
        --backend stmem \
        --stmem-db spacetime-memory-v2 \
        --stmem-host 192.168.1.10 --stmem-port 3001 \
        --answerer-model deepseek-v4-flash-free \
        --judge-model deepseek-v4-flash-free \
        --top-k 200 --max-workers 4 \
        --output-dir /tmp/mem0bench/lme-chain \
        --dataset-path /home/hindsight/spacetime-memory/data/longmemeval_s.json \
        --all-questions \
    >> "$LOGFILE" 2>&1
echo "LongMemEval done $(date)" >> "$LOGFILE"
LME=$(ls -t /tmp/mem0bench/lme-chain/longmemeval_results_*.json 2>/dev/null | head -1)
echo "LONGMEMEVAL_RESULT_FILE=$LME" >> "$MASTER"
if [ -n "$LME" ]; then
    /home/hindsight/spacetime-memory/.venv/bin/python3 - "$LME" >> "$MASTER" <<'PY'
import json, sys
d = json.load(open(sys.argv[1]))
print("LONGMEMEVAL OFFICIAL (Mem0 harness, deepseek via our Zen chain)")
md = d.get("metadata", {})
print(f"  total_questions: {md.get('total_questions')}")
mbc = d.get("metrics_by_cutoff", {})
for cutoff, m in mbc.items():
    o = m.get("overall", {})
    print(f"  {cutoff}: {o.get('accuracy', 0):.2f}% ({o.get('correct')}/{o.get('total')})")
print("MEM0_PUBLISHED_LONGMEMEVAL=94.4 / Mnemosyne 98.9 / Honcho 90.4 / Hindsight 91.4")
PY
fi

# ── 3. MEM0 OFFICIAL BEAM ───────────────────────────────────────────────
echo "=== MEM0 OFFICIAL BEAM ($(date)) ===" >> "$LOGFILE"
timeout 14400 env \
    OTEL_ENABLED=false \
    LLM_BASE_URL=http://localhost:4004/v1 OPENAI_API_KEY=dummy-key \
    PYTHONUNBUFFERED=1 \
    /home/hindsight/spacetime-memory/.venv/bin/python -m benchmarks.beam.run \
        --project-name stmem-chain-beam \
        --backend stmem \
        --stmem-db spacetime-memory-v2 \
        --stmem-host 192.168.1.10 --stmem-port 3001 \
        --answerer-model deepseek-v4-flash-free \
        --judge-model deepseek-v4-flash-free \
        --chat-sizes 100K \
        --dataset-cache-dir /home/hindsight/mem0/evaluation/datasets/beam \
        --output-dir /tmp/mem0bench/beam-chain \
    >> "$LOGFILE" 2>&1
echo "BEAM done $(date)" >> "$LOGFILE"
BEAM=$(ls -t /tmp/mem0bench/beam-chain/beam_results_*.json 2>/dev/null | head -1)
echo "BEAM_RESULT_FILE=$BEAM" >> "$MASTER"
if [ -n "$BEAM" ]; then
    /home/hindsight/spacetime-memory/.venv/bin/python3 - "$BEAM" >> "$MASTER" <<'PY'
import json, sys
d = json.load(open(sys.argv[1]))
print("BEAM OFFICIAL (Mem0 harness, deepseek judge via our Zen chain)")
md = d.get("metadata", {})
print(f"  chat_sizes: {md.get('chat_sizes')}")
mbc = d.get("metrics_by_cutoff", {})
for cutoff, m in mbc.items():
    o = m.get("overall", {})
    print(f"  {cutoff}: {o.get('accuracy', 0):.2f}% ({o.get('correct')}/{o.get('total')})")
print("MEM0_PUBLISHED_BEAM=70.14 (1M) / Mnemosyne 65.2 (100K) / Hindsight 73.4 (100K) / Honcho 63.0 (100K)")
PY
fi

echo "CHAIN COMPLETE $(date)" >> "$MASTER"

# Deliver the full chain summary to the Discord thread via REST (bypasses the
# stuck cron ticker; daemonized so it survives the gateway timeout).
THREAD_ID="1512680047117467740"
# token lives in ~/.hermes/.env or ~/.hermes/config.yaml
TOKEN=$(grep -hoE "DISCORD_BOT_TOKEN=*[A-Za-z0-9_.\-]{20,}" ~/.hermes/.env 2>/dev/null | head -1 | sed -E 's/DISCORD_BOT_TOKEN=*//')
if [ -z "$TOKEN" ]; then
    TOKEN=$(grep -oE "DISCORD_BOT_TOKEN[:=] *[\"']?[A-Za-z0-9_.\-]{20,}" ~/.hermes/config.yaml 2>/dev/null | head -1 | sed -E 's/.*[:=] *[\"'\'']?//')
fi
if [ -n "$TOKEN" ]; then
    python3 - "$MASTER" "$THREAD_ID" "$TOKEN" <<'PY'
import json, sys, urllib.request
master, thread, token = sys.argv[1], sys.argv[2], sys.argv[3]
try:
    body = open(master).read().strip()
except OSError:
    body = "chain master missing"
msg = "**Official Harness Chain Results**\n```\n" + body + "\n```"
data = json.dumps({"content": msg}).encode()
req = urllib.request.Request(
    f"https://discord.com/api/v10/channels/{thread}/messages",
    data=data, method="POST",
    headers={"Authorization": f"Bot {token}", "Content-Type": "application/json"},
)
with urllib.request.urlopen(req, timeout=20) as r:
    print(f"delivered chain results, status={r.status}")
PY
fi
cat "$MASTER"