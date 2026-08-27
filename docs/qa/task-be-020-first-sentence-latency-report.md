# TASK-BE-020 — Shorten Time-To-First-Vetted-Sentence (backend answer stream)

**Branch:** `task/TASK-BE-020-first-sentence-latency` (off `feat/sprint-12-external-voice-websocket`)
**Date:** 2026-08-27
**Related:** ADR-0029 (pilot latency gate), ADR-0013 (guarded SSE streaming), ADR-0037
(first-sentence backend streaming + connect-time warm-up), DEC-002 (no ungrounded amounts),
TASK-BE-017 (warm-up endpoint), TASK-WEB-020/021 (levers 1 + 2).

## Scope of this ticket

Reduce the **non-model-inherent** portion of `backend_first_token` on
`POST /api/conversation/converse-stream` (time for the guarded pipeline to emit its first
vetted sentence). The **model-inherent** first-sentence generation time is explicitly a
separate ticket (**TASK-BE-033**, model choice) and is **not** touched here (LLM
provider/model unchanged).

## Lever chosen (and rationale)

**Warm the reactive LLM streaming path at connect-time warm-up.**

### Why this lever

The streaming answer path (`converse-stream`) calls the LLM through the Spring AI
**reactive** `chatClient…​.stream().content()` (WebClient), a **distinct HTTP client and
reactive pipeline** from the synchronous `…​.call().content()` (RestClient) that the
existing `WarmUpService` (TASK-BE-017) exercised. Warming `.call()` therefore did **not**
warm `.stream()`: the first real `converse-stream` turn still paid the reactive-stack JIT +
the streaming-endpoint connection handshake.

This is the exact **residual finding already recorded in ADR-0037**:

> "`/warm-up` warms embedding + LLM but **not** the full converse critical path (…), leaving
> ~300 ms of turn-1 JIT — follow-up: have `/warm-up` run a full dummy converse so those paths
> warm off-path too."

The live evidence supports the attribution: with TASK-BE-017 warm-up **ON**, the combined
cold pass (2026-07-31, `streaming-voice-qa-report.md`) still shows cold turn-1
`backend_first_token` **p95 1052 ms** vs the warm-steady p50 **733 ms** — a residual tail
that includes the un-warmed reactive streaming path. This lever pre-pays that JIT +
connection off the critical path.

### Why not the alternatives

- **Overlap retrieval with generation / start generation before retrieval:** impossible —
  the retrieved evidence *is* the LLM prompt context, so grounding must complete before the
  first token. Retrieval (embedding + pgvector) is already warmed by the existing embedding
  warm-up.
- **Tighten sentence segmentation to emit the first sentence sooner:** the
  `GuardedSentenceEmitter` already emits each sentence the instant the `SentenceSegmenter`
  closes it (no buffer-till-end). The one-token wait for the whitespace after a terminator is
  a deliberate DEC-002 safeguard (never split a decimal amount on a partial token); relaxing
  it trades safety margin for a sub-token gain and was rejected.
- **Route warm-up through the full `ConverseStreamUseCase` (dummy converse):** would touch
  `ConversationMemoryPort` (append a turn) and violate the warm-up's mandated
  side-effect-free contract. Warming the streaming **generator port** directly achieves the
  same reactive-path warming while staying memory-free. The remaining pure-CPU domain code
  (grounding orchestration, guardrail, segmenter) JIT-warms in sub-ms and is not a measurable
  cold cost.

### Safety properties preserved

- **DEC-002 untouched:** no change to grounding, per-sentence `OutputGuardrail`, or the
  stop-and-hand-off terminal behaviour. The guarded-sentence contract tests are unchanged and
  green.
- **Side-effect-free:** the streaming warm still takes **no** `ConversationMemoryPort`,
  discards every token (`token -> { }`), is repeatable, and **never throws** — a failure is
  recorded as a `warmup_stream` miss (`outcome=error`) exactly like the existing embedding/LLM
  warm-up misses, so a cold provider can never block or delay the first real turn.
- **Default-safe + config-gated:** `voice-support.conversation.warmup.stream-enabled`
  (default `true`). Disabled ⇒ streaming warm-up is skipped and reported warmed (nothing left
  cold by us), so `fullyWarmed` stays honest.

## Files changed

| File | Change |
|---|---|
| `WarmUpService.java` | Added `StreamingAnswerGeneratorPort` + `warmStream()` (drains the reactive stream, records `warmup_stream`, never throws; null generator ⇒ disabled) |
| `WarmUpResult.java` | Added `streamWarmed`; `fullyWarmed()` now includes it |
| `WarmUpResponse.java` | Added `stream_warmed` to the JSON contract (additive, backward-compatible) |
| `WarmUpController.java` | Log line now includes `stream_warmed` |
| `ConversationConfig.java` | Wired `StreamingAnswerGeneratorPort` + `warmup.stream-enabled` flag into the warm-up bean |
| `WarmUpServiceTest.java` / `WarmUpControllerTest.java` | Updated + new coverage (see below) |

## Telemetry changes

- New latency slice **`warmup_stream`** (provider `warmup`, `outcome` success/error),
  symmetric to the existing `warmup_embedding` / `warmup_llm`, so the streaming warm is
  independently timed on the `voice_support.slice` timer and in `[TELEMETRY]` logs.
- The streaming warm also drives the adapter's existing `llm_first_token` / `llm_wording`
  spans once at connect (provider `mistral`/`ollama`) — a real, useful warming of the
  first-token path. No secret or raw provider text is logged; the warm query is a fixed
  constant (`hello`), tokens are discarded.
- `POST /api/conversation/warm-up` response gains `stream_warmed`; `[WARMUP]` log gains
  `stream_warmed`. `backend.first_token` semantics on `converse-stream` are unchanged (still
  first *vetted* sentence).

## `mvn test` result

`BUILD SUCCESS` — **401 tests, 0 failures, 0 errors**, ArchUnit (Hexagonal / ContextBoundary /
NamingConventions) green. Run from `backend/` in this worktree.

Test coverage added/adjusted:
- `warms_embedding_llm_and_stream` — all three paths warmed once.
- `streaming_warm_touches_no_memory` — streaming warm never receives history (memory-free),
  stays warm on repeat.
- `streaming_failure_is_non_blocking` — a throwing streaming generator ⇒ `streamWarmed=false`,
  `warmup_stream error` recorded, no exception escapes.
- `streaming_disabled_is_skipped` — null generator ⇒ reported warmed, **no** `warmup_stream`
  slice emitted.
- `records_success_slices` — `warmup_stream success` timed alongside embedding/LLM.
- `embedding_failure_is_non_blocking` / `sync_llm_failure_is_non_blocking` — one failing step
  never blocks the others; streaming still warmed.
- Controller tests assert `stream_warmed` in the response and `fully_warmed` gating.

DEC-002 / incremental-delivery contract (unchanged, still green):
- `StreamingConversationServiceTest.delivers_first_sentence_before_full_answer` — first vetted
  sentence reaches the consumer **before** the second is generated (service-level incremental
  delivery).
- `StreamingConversationServiceTest.ungrounded_amount_stops_stream` — no sentence emitted
  before vetting; a mid-stream ungrounded amount stops emission + hands off.

## Adversarial code review (self-review)

Score: **93/100 — QA gate Pass.**

### Blocking findings
None.

### Non-blocking findings

| Severity | Finding | Recommendation |
|---|---|---|
| Low | `WarmUpService` constructor now takes 6 params (was 5), above the ≤3 guideline. | Pre-existing style; a `WarmUpSettings` record could group `warmQuery`/`language`/flag. Accepted as residual to keep the diff minimal. |
| Low | Streaming warm roughly **doubles** connect-time warm-up wall clock (a second full generation, ~0.7–1.4 s). | Off the critical path (runtime fires it async at connect with a generous timeout, `VOICE_BACKEND_WARMUP`); disable via `warmup.stream-enabled=false` if connect budget matters. |
| Info | For a pure-streaming pilot the sync `.call()` warm is arguably redundant, but `/converse` remains the non-streaming fallback, so both stay warmed. | Optional future: gate the sync warm too. |

### Dimension notes
- **Functional alignment:** matches the ticket objective (reduce non-model backend
  first-sentence overhead) and closes the ADR-0037 streaming-path residual. Model-inherent
  time correctly deferred to TASK-BE-033.
- **Architecture:** hexagonal preserved — warm-up is an application service depending only on
  domain ports; no domain change; bean wired in `DomainServiceConfig`-style config. ArchUnit
  green.
- **Test evidence:** all new library surface (the streaming generate path) is unit-covered;
  DEC-002 contract tests unchanged and green.
- **Observability:** new `warmup_stream` slice + `stream_warmed` flag; sanitized; no secret
  leak.
- **Failure modes:** streaming warm failure recorded as a miss, never throws, never blocks the
  first real turn (parity with embedding/LLM warm).
- **Security/privacy:** fixed warm query, tokens discarded, api-key gate unchanged.

## Pending live measurement (remaining QA gate — NOT run here)

A full LIVE re-score needs the real Gradium STT/TTS + Mistral infra and the tst OTel
collector, which are not drivable from this environment. **No latency numbers are fabricated.**
The remaining gate mirrors the WEB-035/036 + ADR-0037 lever-2 procedure:

1. Deploy this backend build; runtime with `VOICE_BACKEND_STREAM=1`, `VOICE_BACKEND_WARMUP=1`,
   `voice-support.conversation.warmup.stream-enabled=true` (default).
2. **A/B micro-benchmark** on `converse-stream` first-sentence time, cold backend (fresh JVM +
   Ollama embedding evicted `ollama stop nomic-embed-text`):
   - **Control:** `warmup.stream-enabled=false` (streaming path left cold, as today).
   - **Treatment:** `warmup.stream-enabled=true`.
   Confirm at connect: `[WARMUP] … stream_warmed=true` and a `warmup_stream success` slice.
3. **Live streaming pass** (headless WebRTC client, 5-question script, cold + warm) →
   `python3 scripts/streaming_latency_report.py --input <telemetry.jsonl>` for
   `backend_first_token` and `voice_to_first_audio` p50/p95/p99, evaluating the ADR-0029 gate
   (m2e p95 ≤ 1.5 s).
4. **Expected effect (to verify, not claimed):** the residual turn-1 `backend_first_token` p95
   tail (currently ~1052 ms with sync-only warm-up) drops toward the warm-steady band
   (~733 ms p50) as the reactive-path JIT + streaming-endpoint connection is pre-paid. Warm
   **steady** p50 is dominated by RAG + model first-sentence time and is expected to be flat
   (model portion is TASK-BE-033).

Until that live p95 is captured, **no pilot SLO is claimed**; this ticket delivers the
implementation + unit tests + adversarial review + OTel only.
