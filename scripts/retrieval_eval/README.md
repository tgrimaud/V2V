# Retrieval-quality eval harness (TASK-BE-027 / ADR-0032)

Offline, repeatable measurement against `POST /api/conversation/retrieve`. It is the
**decision gate for OQ-008 / ADR-0032**: the choice between the remaining levers (MMR →
hybrid → cross-encoder rerank → Qdrant) is driven by these numbers, not by intuition. Needs
no pilot/external access — only the backend, pgvector and a loaded corpus.

> **Important — what "success" means here.** `/retrieve` runs the whole pre-LLM grounding
> pipeline: **input guardrail → retrieval → confidence guardrail**. A blocked guardrail
> decision returns **no evidence**, so a miss is not necessarily a retrieval failure. The
> harness therefore classifies every miss as a **guardrail block** (`answerable=false`, no
> evidence — e.g. an `OFF_TOPIC` verdict) or a **retrieval eviction** (evidence returned but
> the answer chunk is not in top-k). This is the BUG-003 lesson: pick the right lever
> (guardrail/threshold vs MMR/hybrid/Qdrant) instead of misattributing a downstream block to
> retrieval.

## What it measures

For each question the eval set carries several **phrasing variants** (including a
greeting-prefixed one — the BUG-003 brittleness axis) and a set of `acceptable_source_ids`
derived from the KB **title/section** semantics (not from the ranking being measured, so
recall is non-circular). A `source_id` is a chunk's article id: the CSV `document_id`
(shared across the FR and EN corpora) or a markdown filename (e.g. `telecom-faq.md`).

- **recall@k** (k = 4, 8): fraction of variants whose top-k contains an acceptable source.
- **MRR**: mean reciprocal rank of the first acceptable source.
- **phrasing-stability** (= 1 − flip-rate): fraction of questions whose variants all agree on
  the top-k outcome. A "flip" is a trivial phrasing change moving the answer in/out of top-k.
- **miss classification**: per scope, the count of **guardrail-block** vs **retrieval-eviction**
  misses; per question, the **flip cause** (guardrail / retrieval / mixed).

Reported overall and broken down **per language and per domain**, so a gap (e.g. EN support)
is never hidden inside an aggregate.

> `--top-k` is clamped to ≥ 8 because recall@8 and stability@8 need at least 8 results.

## Prerequisites

- Backend running on `:8080` with pgvector + Ollama embeddings and the corpus synced
  (markdown FAQs + `articles.csv` / `articles-fr.csv`). Confirm with:
  ```bash
  curl -s localhost:8080/api/conversation/retrieve -X POST \
    -H 'Content-Type: application/json' -d '{"question":"facture","top_k":1}'
  ```
- Python 3.11+ (stdlib only — no third-party dependency).

## Run

```bash
# Unit tests for the metric math (no backend needed)
python3 -m unittest discover -s scripts/retrieval_eval/tests

# Baseline against the live backend (writes reports/baseline-<date>.{md,json})
python3 scripts/retrieval_eval/run_eval.py --base-url http://localhost:8080 --top-k 8

# Options
#   --domain-mode none|intended   none = retrieval ceiling (no domain filter, default);
#                                  intended = send each question's domain (mirrors routing)
#   --api-key <value>             sends x-api-key when the backend requires a shared secret
#   --label <name>                report filename label (default: today's date)
```

## Acceptance bar (ADR-0032, proposed)

`recall@8 ≥ 0.90` **and** `phrasing-stability ≥ 0.90` on the eval set → stay on pgvector, no
further lever needed. Below that, add the next cheapest lever (MMR → hybrid → rerank) and
re-run; only a fired Qdrant trigger (see ADR-0032) justifies the engine change.

## Extending the eval set

Add questions to `eval_set.json`. Keep `acceptable_source_ids` grounded in article
titles/sections (verify against `articles-fr.csv` / `knowledge-base/*.md`), include at least
one greeting-prefixed variant, and cover both FR and EN. Re-run to refresh the baseline.
