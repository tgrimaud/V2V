# ADR-0029: Pilot Latency Criterion With A Real Backend, Market Baseline, And The Cascade-vs-Speech-to-Speech Fork

## Status

Accepted — revises the pilot acceptance criterion of
[ADR-0018](ADR-0018-voice-latency-targets-and-slo-measurement.md) (the ADR-0018
latency **taxonomy** and measurement method remain in force) and resolves
[OQ-005](../../../product-backlog/open-questions/v1-open-questions.md#oq-005---pilot-latency-acceptance-context).
Reaffirms [ADR-0012](ADR-0012-modular-voice-pipeline-over-realtime-api.md).

## Status update — TASK-WEB-022 (2026-08-06): gate unchanged at 1.5 s, OPEN

The pilot gate **stays at mouth-to-ear p95 ≤ 1.5 s** (no number change, Product/Architecture
sign-off 2026-08-06). It is **currently FAILED**: the last combined live pass (levers 1+2,
cold) recorded m2e p95 ≈ **2142 ms** (margin −642 ms). TASK-WEB-022 resolved the "levers ship
OFF" half of the finding by flipping the **validated** levers to their code defaults —
`VOICE_BACKEND_STREAM` ON (strict-win first-sentence streaming), end-of-turn hold 350 ms
(0/10 false-cut live), backend warm-up ON — so a default pilot run is no longer *slower* than
the measured numbers. **STT pre-warm stays OFF** (unvalidated idle-socket). Closing the
residual ~640 ms is **not** a defaults problem: it is handed to **TASK-STT-014** (STT
finalize-tail) + **TASK-BE-020** (first-sentence backend generation), then a **live
re-measurement** on the tst collector (blocked on the platform open inputs — TLS/TURN/NAT +
centralized aggregation from TASK-OPS-007). No pilot SLO is claimed until that live p95 is
captured. Revising the number was explicitly considered and **rejected** here (the market
data in this ADR shows > 1.5 s breaks deals); the bar holds and the engineering path closes it.

**Follow-up (2026-08-15, global-review decision #2):** the reference mouth-to-ear
measurement — a single **warm, co-located WebRTC + real backend (`--backend http`)** session
that replaces the current ~1.54 s *projection* — is now ticketed as **TASK-WEB-032** (High).
The stale `< 800 ms` references in the Sprint-7 `docs/qa/answer-engine-qa-report.md` were
annotated as superseded by this ADR the same day. OQ-005 already records this gate as decided.

## Context

ADR-0018 set the pilot acceptance criterion at `time_to_first_audio` **p95 < 800 ms**.
That number was met in Sprint 6 (761.5 ms p95, TASK-WEB-011) but **against a stub
backend** — no RAG, no LLM. Once the real answer engine (EPIC-005) is in the loop:

| Measurement | `stt` p95 | `backend_first_token` p95 | `tts_first_audio` p95 | `time_to_first_audio` p95 |
|---|---:|---:|---:|---:|
| Sprint 6 gate met (stub backend) | 381 ms | ~0 ms | 381 ms | **761.5 ms** (PASS) |
| Real backend, BE-010 | 373 ms | 789 ms | 381 ms | **≈ 1.54 s** (FAIL) |
| Real backend, BE-011 (trimmed prompt + configurable top-K) | 373 ms | **653 ms** | 381 ms | **≈ 1.41 s** (FAIL) |

Sources: `docs/qa/answer-engine-qa-report.md` (+ BE-011 addendum),
`docs/qa/streaming-latency-warm-prewarm.json`.

Two structural facts drove this ADR:

1. **STT and TTS are at Gradium's streaming floors.** Sprint 6 already extracted the
   big wins (STT tail 1389 → 373 ms; TTS first audio 484 → 381 ms). The remaining
   headroom is ~50–100 ms at high risk (commit-before-final was rejected for word
   loss). STT + TTS ≈ **754 ms** combined. To keep the composite under 800 ms with a
   real backend, STT + TTS would have to fit in ~147 ms — **not achievable** on the
   Gradium cascade. Backend prompt levers (TASK-BE-011) cut the tail but cannot close
   a ~600 ms structural gap; the LLM median first token (~330 ms) is a cloud
   network/prefill floor.

2. **The 800 ms number was never validated against the way the market measures
   latency.** ADR-0018 defines `time_to_first_audio` from **end-of-turn acceptance**
   to first playable frame — it **excludes** the ~500 ms end-of-turn silence hold and
   the WebRTC/browser `channel_egress` (both still uninstrumented, TASK-WEB-014). The
   industry measures **"mouth-to-ear"**: from the instant the user stops speaking to
   the instant they hear the first audio. Our comparable mouth-to-ear number today is
   ~500 ms (endpointing) + ~1.41 s (composite) + egress ≈ **~2 s** — we were
   comparing a middle-of-chain slice to end-to-end market figures.

### Market baseline (2026, mouth-to-ear)

| Source | Architecture | p50 | p95 | Note |
|---|---|---:|---:|---|
| DestiLabs 2026 fleet (10+ prod deployments) | cascade + S2S | 680 ms | 1180 ms | ">1200 ms p50 feels broken" |
| DILR.ai (enterprise production) | prod | ~680 ms | 1400–1700 ms under barge-in | ">1500 ms breaks deals" |
| Deepgram + Claude + ElevenLabs (lab bench) | cascade, tuned | 480 ms | 624 ms | best-in-class lab |
| Pipecat + Claude + Cartesia (lab bench) | cascade (closest to ours) | 410 ms | 540 ms | ultra-fast TTS |
| OpenAI Realtime / Gemini Live | **speech-to-speech** | 230–300 ms | ~295 ms | no TTFT→TTFB stacking |
| Human turn-taking (reference) | — | ~200 ms | — | delays >800 ms → +40 % abandonment |

Vendor-published numbers are lab best-case; production runs 30–80 % higher (Retell
publishes ~800 ms, lands 1–1.4 s in EU). Takeaways:

- **For a cascaded STT→LLM→TTS stack with a cloud LLM, an 800 ms p95 mouth-to-ear is
  best-in-class-lab territory**, not a realistic pilot bar. Production cascades cluster
  at ~1.0–1.4 s p95.
- **Sub-second mouth-to-ear in production is essentially a speech-to-speech property**
  (one model emits audio tokens directly, no TTFT-then-TTFB stacking).

### The OpenAI direction clarified

"We will move to OpenAI" covers two very different architectures:

- **A. OpenAI as the cascade chat LLM** (replace Mistral for the wording step, behind
  the existing ports — ADR-0006, DEC-011). Helps `backend_first_token`; **stays a
  cascade** → does not reach 800 ms.
- **B. OpenAI Realtime (speech-to-speech, gpt-realtime-2, GA 2026-05-07)** — the only
  route to sub-second, but: (i) measured TTFA is **1.12 s (`minimal` reasoning) to
  2.33 s (`high`)** (Artificial Analysis) — not the sub-300 ms of gpt-4o-realtime /
  Gemini Live; (ii) an audio-in/audio-out model makes RAG grounding, DEC-002 (the LLM
  must never compute or state an amount absent from deterministic evidence),
  guardrails, and conversation memory materially harder to enforce — exactly the
  control ADR-0012 chose the modular cascade to keep.

## Decision

1. **Revise the pilot acceptance criterion** for the target V1 voice path (Gradium
   cascade + real backend, warm, co-located), replacing the stub-era `p95 < 800 ms`:
   - **Primary (mouth-to-ear):** `voice_to_first_audio` (user stops speaking →
     first audible frame, i.e. end-of-turn hold + `time_to_first_audio` composite +
     `channel_egress`) **p95 ≤ 1.5 s**, aligned with the market production-viability
     ceiling (deals break above ~1.5 s).
   - **Engineering sub-target (unchanged definition):** `time_to_first_audio`
     (end-of-turn acceptance → first playable frame) **p95 ≤ 1.2 s**.
   - **Aspirational experience target (unchanged):** ~700 ms to the first audible
     sentence — now explicitly flagged as reachable only via a speech-to-speech
     architecture, not the V1 cascade.

2. **Prerequisite to any pilot sign-off or SLO claim:** instrument true mouth-to-ear
   — fold `channel_egress` and the end-of-turn hold into one correlation-id timeline
   and report p50/p95/p99 (**TASK-WEB-014**, the ADR-0018 known gap). No latency
   acceptance is recorded against a partial composite. **Status (TASK-WEB-014):** the
   instrumentation now exists — the `voice_to_first_audio` composite folds the
   end-of-turn hold + post-EOT path + WebRTC runtime `channel_egress`, the
   `streaming_latency_report` evaluates the ADR-0029 gate, and the headless client
   logs a browser-audible first-audible proxy for the residual network/playout gap.
   The remaining step before sign-off is capturing a **warm live sample against the
   real backend** and recording its p50/p95/p99 in the QA report.

3. **Reaffirm ADR-0012 (modular cascade) for V1.** We do **not** chase sub-800 ms by
   moving the conversation loop into a speech-to-speech provider, because that would
   surrender the RAG / DEC-002 / guardrail / memory control the cascade exists to
   protect. "OpenAI" in V1 means **option A** (cascade chat provider behind ports).

4. **Speech-to-speech is a future stretch, not a V1 lever.** A sub-second criterion is
   revisited only if and when a speech-to-speech architecture is separately evaluated
   and shown to preserve grounding, DEC-002, guardrails, and memory. That evaluation
   requires its own ADR (superseding or amending ADR-0012); until then, ADR-0012
   stands.

5. **Do not spend further effort shrinking Gradium STT/TTS for the gate.** They are at
   the provider floor; the latency conversation moves to the answer engine and the
   criterion, not the voice edges. Co-location and a faster STT/TTS provider benchmark
   remain optional, low-priority levers (pursue only if a provider beats the Gradium
   floor by >100 ms per slice).

## Consequences

- The pilot latency bar becomes **measurable and honest against market data**: a
  cascade V1 is judged at ~1.2 s (engineering) / ~1.5 s (mouth-to-ear), not an
  unreachable 800 ms.
- ADR-0018's taxonomy, measurement method, and per-slice reporting stay in force; only
  the acceptance **number** and the addition of the mouth-to-ear metric change.
- The current real-backend path (~1.41 s `time_to_first_audio` p95, BE-011) is
  **within the revised engineering sub-target's neighborhood but not yet inside it**;
  the mouth-to-ear composite is now instrumented (TASK-WEB-014) and is the true gate —
  its measured p95 is pending a warm live sample against the real backend.
- A production SLO still requires the ADR-0010 operational controls (dashboards,
  alerting, degraded-mode + provider-outage tests) on top of the measured baseline.
- OQ-005 is resolved: acceptance conditions, metrics, and the cascade decision are now
  recorded; remaining OQ-005 sub-items (which journeys count, fixture-vs-live provider
  mix, barge-in authority) are folded into TASK-WEB-014 and the QA latency plan.

## Alternatives Considered

- **Keep 800 ms as a hard pilot gate:** rejected — unreachable for a cascade with a
  real cloud LLM; it would either block the pilot indefinitely or push the team to
  abandon the modular architecture for the wrong reason (a stub-era number).
- **Adopt speech-to-speech (OpenAI Realtime / Gemini Live) now to hit sub-second:**
  rejected for V1 — conflicts with ADR-0012; weakens RAG/DEC-002/guardrail control;
  and gpt-realtime-2's real TTFA (1.12–2.33 s) shows S2S is not an automatic latency
  win once reasoning is enabled.
- **Drop the number and say "under ~1.5 s":** rejected — too vague for engineering
  validation; ADR-0018 already resolved this class of drift. We keep explicit p95
  targets plus the measurement basis.
- **Keep squeezing Gradium STT/TTS:** rejected — at the provider floor; ~50–100 ms at
  high regression risk, no path to closing a ~600 ms gap.

## Related Documents

- [ADR-0018 — Voice latency targets and SLO measurement](ADR-0018-voice-latency-targets-and-slo-measurement.md)
- [ADR-0012 — Modular voice pipeline over realtime API](ADR-0012-modular-voice-pipeline-over-realtime-api.md)
- [ADR-0010 — Industrialization requires contracts, SLOs and observability](ADR-0010-industrialization-requires-contracts-slos-and-observability.md)
- [ADR-0006 — Mistral chat and Ollama embeddings](ADR-0006-mistral-chat-and-ollama-embeddings.md)
- `docs/qa/answer-engine-qa-report.md` (BE-010 + BE-011 latency evidence)
- `product-backlog/open-questions/v1-open-questions.md` (OQ-005)
- `product-backlog/decisions/v1-decisions.md` (DEC-002, DEC-011)

### External sources (market baseline, accessed 2026-07-20)

- DestiLabs, "2026 AI Voice Agent Benchmark: Latency & Cost per Minute" —
  https://www.destilabs.com/blog/ai-voice-agent-benchmark-2026
- DILR.ai, "Voice agent latency benchmarks: enterprise reality" —
  https://www.dilr.ai/blog/voice-agent-latency-quality-benchmarks
- Bluejay, "Metrics Every Voice AI Team Should Track [2026]" —
  https://getbluejay.ai/resources/metrics-every-voice-ai-team-should-track
- "I Benchmarked 5 Voice AI Stacks. Only 2 Stayed Under 300ms." (dev.to) —
  https://dev.to/kenimo49/i-benchmarked-5-voice-ai-stacks-only-2-stayed-under-300ms-2bka
- SoftwareSeni / AnthemCreation on GPT-Realtime-2 TTFA (Artificial Analysis figures) —
  https://www.softwareseni.com/gpt-realtime-2-and-the-new-voice-model-tier/
