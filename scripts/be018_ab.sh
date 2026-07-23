#!/usr/bin/env bash
# TASK-BE-018 QA A/B driver: runs the backend once with a given answer-sentence budget,
# fires a fixed FR/EN question set at /converse, and captures the answer + correlation id
# so answer length and the llm_wording slice can be parsed from the log afterwards.
# Usage: be018_ab.sh <budget> <tag>   (e.g. be018_ab.sh 3 b3  |  be018_ab.sh 0 b0)
set -u
BUDGET="$1"; TAG="$2"
ROOT="/Users/tgrimaud/Workspace/Code/BMad/voice-support-bot"
JAR="$ROOT/backend/target/voice-support-backend-0.1.0-SNAPSHOT.jar"
PORT=8081
LOG="/tmp/be018_${TAG}.log"
OUT="/tmp/be018_${TAG}.jsonl"
: > "$OUT"

set -a; . "$ROOT/.env"; set +a
export LLM_MAX_ANSWER_SENTENCES="$BUDGET"
export JAVA_HOME="${JAVA_HOME:-/opt/homebrew/Cellar/openjdk/25.0.2/libexec/openjdk.jdk/Contents/Home}"

echo "[driver] starting backend budget=$BUDGET tag=$TAG on :$PORT (java=$JAVA_HOME)"
"$JAVA_HOME/bin/java" -jar "$JAR" --server.port=$PORT > "$LOG" 2>&1 &
BPID=$!
echo "[driver] pid=$BPID"

# wait for health (max ~60s)
for i in $(seq 1 60); do
  if curl -s -m2 "localhost:$PORT/actuator/health" | grep -q '"status":"UP"'; then
    echo "[driver] backend UP after ${i}s"; break
  fi
  sleep 1
done

# FR/EN question set: grounded (billing/support), a BUG-004 greeting turn, and off-topic.
declare -a QS=(
  "g|fr|Pourquoi ma facture est-elle plus élevée ce mois-ci ?"
  "g|fr|C'est quoi la proration sur ma facture ?"
  "g|fr|Comment résilier mon abonnement internet ?"
  "g|fr|Je n'ai plus internet depuis ce matin, que puis-je faire ?"
  "b|fr|Bonjour, j'ai un problème avec ma connexion internet."
  "g|en|Why is my bill higher this month?"
  "g|en|How do I set up my new router?"
  "g|en|What is data roaming and how is it charged?"
  "o|fr|Quel temps fera-t-il demain ?"
  "o|en|Who won the football match yesterday?"
)

n=0
for entry in "${QS[@]}"; do
  n=$((n+1))
  kind="${entry%%|*}"; rest="${entry#*|}"; lang="${rest%%|*}"; q="${rest#*|}"
  cid="be018-${TAG}-${n}"
  resp=$(curl -s -m 30 -X POST "localhost:$PORT/api/conversation/converse" \
    -H 'Content-Type: application/json' \
    -d "$(python3 -c 'import json,sys; print(json.dumps({"transcript":sys.argv[1],"conversationId":sys.argv[2],"correlationId":sys.argv[2],"channel":"api"}))' "$q" "$cid")")
  # ADR-0021 sync endpoint on this branch: POST /api/conversation/converse -> {text, confidence}
  echo "{\"cid\":\"$cid\",\"kind\":\"$kind\",\"lang\":\"$lang\",\"q\":$(python3 -c 'import json,sys;print(json.dumps(sys.argv[1]))' "$q"),\"resp\":$resp}" >> "$OUT"
  echo "[driver] $cid ($kind/$lang) done"
done

echo "[driver] stopping backend pid=$BPID"
kill "$BPID" 2>/dev/null
wait "$BPID" 2>/dev/null
echo "[driver] finished tag=$TAG -> $OUT / $LOG"
