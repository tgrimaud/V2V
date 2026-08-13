# A/B — TASK-BE-029 Query Greeting-Normalization (live local corpus, 2026-08-13)

Same build (`voice-support-backend-0.1.0-SNAPSHOT`, BE-029), only the
`voice-support.knowledge.retrieval.query-normalization.enabled` flag changed. Backend on
`:8081`, pgvector `pg16` (10 163 chunks) + Ollama `nomic-embed-text`, `--top-k 8`, eval set
`scripts/retrieval_eval/eval_set.json` (14 questions / 29 variants). MMR left OFF (default).

## Hypothesis under test

TASK-BE-027 attributed the single baseline retrieval eviction (`sup-fr-slow`) to the leading
greeting on its second variant: stripping `"Bonjour, "` before embedding should make the greeting
variant retrieve the same evidence as the bare variant, lifting phrasing-stability to 1.0 for that
question with no overall regression.

## Result

| Arm | recall@4 | recall@8 | MRR | stability | guardrail-block | retrieval-eviction | normalize invocations |
|---|---|---|---|---|---|---|---|
| Normalization OFF | 0.828 | **0.897** | 0.767 | **0.786** | 2 | 1 | 0 |
| Normalization ON | 0.828 | **0.897** | 0.767 | **0.786** | 2 | 1 | 13 |

**Strictly neutral.** Every metric is identical with normalization on or off. The normalizer fired
13 times (correctly stripping greetings, e.g. `original_len=41 normalized_len=32`) with **zero
regression** — but **zero gain**.

## Why the hypothesis is wrong (root-cause correction)

The eviction persists after stripping the greeting. Per-variant evidence for `sup-fr-slow`
(acceptable = `telecom-faq.md` / `13` / `854`):

| Variant | Embedded query (normalization ON) | Top-8 source ids | Answer in top-8? |
|---|---|---|---|
| `"Ma connexion internet est très lente."` | *(unchanged)* | `305, telecom-faq.md, 230, telecom-faq.md, 79, 864, 317, 79` | ✅ rank 2 |
| `"Bonjour, internet est très lent chez moi."` | `"internet est très lent chez moi."` | `305, 305, 366, 932, 79, 235, 317, 11` | ❌ absent |

The two variants differ in **more than the greeting**: the core wording (`"internet est très lent
chez moi"` vs `"Ma connexion internet est très lente"`) is what moves the embedding out of range of
the answer chunk. Removing `"Bonjour, "` leaves `"internet est très lent chez moi."`, which still
does **not** retrieve `telecom-faq.md`. **The greeting was mis-attributed as the cause; the miss is
a core-phrasing recall miss.**

## Decision

- **TASK-BE-029 does NOT fix the eviction** — closed under its own condition ("if the harness shows
  no phrasing-stability gain, close as not needed with that evidence").
- **Default OFF** (consistent with TASK-BE-028): shipped as a tested, env-toggleable robustness
  guard (`KB_RETRIEVAL_QUERY_NORMALIZATION_ENABLED`). It strips greetings correctly with zero
  regression, so it is safe to enable if real voice traffic later shows a greeting-only recall flip
  that the eval set does not contain.
- **True next lever for `sup-fr-slow`** (OQ-008): phrasing-robust recall — e.g. hybrid lexical+dense
  fusion or query expansion — or enriching the eval set with a greeting-only differentiator to keep
  the two variants identical except for the greeting. Not query normalization, not MMR.

## Reproduction

```bash
cd backend && mvn -o package -DskipTests
# OFF
KB_RETRIEVAL_QUERY_NORMALIZATION_ENABLED=false \
  java -jar target/voice-support-backend-0.1.0-SNAPSHOT.jar --server.port=8081 \
  --logging.level.com.voicesupport.knowledge.infrastructure.adapter.out.observability=DEBUG
python3 scripts/retrieval_eval/run_eval.py --base-url http://localhost:8081 --top-k 8 \
  --label be029-normoff-2026-08-13
# ON
KB_RETRIEVAL_QUERY_NORMALIZATION_ENABLED=true \
  java -jar target/voice-support-backend-0.1.0-SNAPSHOT.jar --server.port=8081 \
  --logging.level.com.voicesupport.knowledge.infrastructure.adapter.out.observability=DEBUG
python3 scripts/retrieval_eval/run_eval.py --base-url http://localhost:8081 --top-k 8 \
  --label be029-normon-2026-08-13
```

Artifacts: `reports/baseline-be029-normoff-2026-08-13.{json,md}`,
`reports/baseline-be029-normon-2026-08-13.{json,md}`.
