#!/usr/bin/env bash
# Reproducible local runner for one TASK-BE-033 / ADR-0045 benchmark candidate.
#
# Boots the backend jar with a chosen chat provider/model, waits for readiness, runs the
# benchmark harness against the backend's own log (so server [TELEMETRY] slices are captured),
# then stops the backend. Re-runnable for any candidate — including OpenAI once a key exists:
#
#   # EU baseline
#   scripts/llm_benchmark/run_local_candidate.sh mistral-small mistral-api mistral-small-latest \
#       MISTRAL_CHAT_MODEL=mistral-small-latest
#   # co-located Ollama (raise embedding/retrieval budgets: chat+embed share one Ollama)
#   scripts/llm_benchmark/run_local_candidate.sh ollama-llama31-8b ollama llama3.1:8b \
#       OLLAMA_CHAT_MODEL=llama3.1:8b EMBEDDING_TIMEOUT_MS=30000 RETRIEVAL_TIMEOUT_MS=35000 \
#       LLM_TIMEOUT_MS=60000 LLM_STREAM_TIMEOUT_MS=60000
#   # OpenAI gpt-4o-mini — export OPENAI_API_KEY first (US egress = OQ-009, spike measurement only)
#   OPENAI_API_KEY=sk-... scripts/llm_benchmark/run_local_candidate.sh \
#       openai-gpt-4o-mini openai gpt-4o-mini OPENAI_CHAT_MODEL=gpt-4o-mini
#
# Then merge:  python3 scripts/llm_benchmark/compare.py 'scripts/llm_benchmark/reports/bench-*.json'
#
# Prereqs: a running Postgres/pgvector with the KB synced + Ollama for embeddings (nomic-embed-text),
# a built jar (mvn -q -DskipTests package), and provider creds in the repo-root/.env or the env.
set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
JAR_GLOB="$REPO/backend/target/voice-support-backend-*.jar"
LABEL="${1:?usage: run_local_candidate.sh LABEL PROVIDER MODEL [KEY=VALUE ...]}"
PROVIDER="${2:?missing PROVIDER (mistral-api|ollama|openai)}"
MODEL="${3:?missing MODEL}"
shift 3
LOG="/tmp/be033_${LABEL}.log"
BASE_URL="${BASE_URL:-http://localhost:8080}"
REPS="${REPS:-3}"

# --- locate a JDK: honor $JAVA_HOME, else macOS java_home, else Maven's runtime ---
if [ -z "${JAVA_HOME:-}" ] || [ ! -x "${JAVA_HOME:-}/bin/java" ]; then
  if [ -x /usr/libexec/java_home ] && /usr/libexec/java_home >/dev/null 2>&1; then
    JAVA_HOME="$(/usr/libexec/java_home)"
  else
    JAVA_HOME="$(mvn -v 2>/dev/null | sed -n 's/^Java home: //p')"
    [ -z "$JAVA_HOME" ] && JAVA_HOME="$(mvn -v 2>/dev/null | sed -n 's/.*runtime: //p')"
  fi
fi
JAVA="${JAVA_HOME:+$JAVA_HOME/bin/java}"; JAVA="${JAVA:-java}"
JAR="$(ls -1 $JAR_GLOB 2>/dev/null | head -1)"
[ -x "$JAVA" ] || { echo "[be033] no java runtime (set JAVA_HOME)"; exit 1; }
[ -n "$JAR" ] || { echo "[be033] jar not built — run: (cd backend && mvn -q -DskipTests package)"; exit 1; }

cd "$REPO"
[ -f ./.env ] && { set -a; . ./.env; set +a; }
export LLM_PROVIDER="$PROVIDER" CONVERSATION_API_KEY="" SERVER_PORT="${SERVER_PORT:-8080}"
for kv in "$@"; do export "$kv"; done

echo "[be033] label=$LABEL provider=$PROVIDER model=$MODEL jar=$(basename "$JAR")"
: > "$LOG"
"$JAVA" -jar "$JAR" >> "$LOG" 2>&1 &
PID=$!
trap 'kill $PID 2>/dev/null' EXIT
for i in $(seq 1 120); do
  grep -q "Started VoiceSupportApplication" "$LOG" 2>/dev/null && { echo "[be033] backend up (${i}s)"; break; }
  kill -0 $PID 2>/dev/null || { echo "[be033] BACKEND DIED — tail:"; tail -20 "$LOG"; exit 1; }
  sleep 1
done
sleep 2

python3 "$REPO/scripts/llm_benchmark/run_benchmark.py" \
  --label "$LABEL" --model "$MODEL" --reps "$REPS" --warmup 1 \
  --telemetry-log "$LOG" --base-url "$BASE_URL" \
  --out-dir "$REPO/scripts/llm_benchmark/reports"
RC=$?

kill $PID 2>/dev/null; wait $PID 2>/dev/null; trap - EXIT
echo "[be033] done label=$LABEL rc=$RC (backend log: $LOG)"
exit $RC
