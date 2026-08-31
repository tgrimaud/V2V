# V1 Open Questions

## OQ-001 - Customer Identification By Phone And Web Voice Channel

**Status:** Open  
**Owner:** Product / BSS / Security  
**Impacts:** EPIC-001, EPIC-004, EPIC-005, EPIC-008

### Question

How is the customer identity established on each V1 channel?

### Why It Matters

The bot must explain invoices only for a customer identified with enough
confidence. The identification level determines BSS access, what can be spoken or
displayed, and when escalation is required.

### Needed Decision

- Identity source for the phone journey.
- Identity source for the web voice journey.
- Minimum confidence level for invoice access.
- Product behavior when identity is incomplete or conflicting.

---

## OQ-002 - Minimum Proof Threshold For Answering Without Escalation

**Status:** Open  
**Owner:** Product / Billing SME / Legal  
**Impacts:** EPIC-003, EPIC-006, EPIC-008

### Question

What evidence level is required for the bot to confirm a cause of invoice delta
without escalating to a human advisor?

### Why It Matters

An unproven answer may mislead the customer. A threshold that is too strict may
also create unnecessary escalations.

### Needed Decision

- Causes the bot may confirm alone.
- Causes the bot may present as probable.
- Causes that require escalation.
- Expected wording when certainty is insufficient.

### Implementation Note (2026-07-27, ADR-0034 / BUG-005)

A **provisional** three-band retrieval-confidence policy now exists pending this decision:
below `confidence-threshold` (0.5) → advisor hand-off; between it and `clarify-threshold`
(0.62) → ask the customer to clarify; at/above → answer. These are engineering placeholders
tuned on observed similarity scores, **not** a validated billing-proof threshold — the
definitive values (and whether a billing answer with no confidence must be treated as
degraded) remain gated by this OQ and the billing answer engine.

---

## OQ-003 - BSS Data Availability And Granularity

**Status:** Open  
**Owner:** BSS owner  
**Impacts:** EPIC-001, EPIC-002, EPIC-003, EPIC-010

### Question

Which BSS data is available in read-only mode to explain invoice deltas?

### Why It Matters

The comparison engine and customer-visible evidence depend directly on available
granularity: invoice lines, usage, discounts, prorations, options, taxes, billing
events and offer changes.

### Needed Decision

- Data accessible in V1.
- Available history depth.
- Expected freshness.
- Access and confidentiality limits.
- Whether any structured invoice-line endpoint can replace PDF extraction later.

---

## OQ-004 - Invoice PDF Extraction Reliability And Fixture Coverage

**Status:** Open  
**Owner:** Product / BSS / QA  
**Impacts:** EPIC-002, EPIC-003, EPIC-010

### Question

Which real invoice PDFs and extraction quality thresholds are required to validate
the V1 explanation behavior?

### Why It Matters

ADR-0005 makes invoice PDF extraction the V1 evidence path until a validated
structured line endpoint exists. Product behavior depends on whether extraction
is `parseable`, `partial` or `unusable`.

### Needed Decision

- Minimum anonymized PDF samples for pilot validation.
- Required fixture journeys: nominal, discount expiry, overage, proration,
  insufficient data, partial/unusable extraction.
- Acceptance threshold for treating extracted lines as confirmed evidence.
- Expected customer wording for partial or unusable extraction.

---

## OQ-005 - Pilot Latency Acceptance Context

**Status:** ✅ Decided (2026-07-20) — resolved by
[ADR-0029](../../docs/architecture/adrs/ADR-0029-pilot-latency-criterion-real-backend-and-market-baseline.md).
The stub-era `p95 < 800 ms` is revised for the real-backend Gradium cascade to a
**mouth-to-ear p95 ≤ 1.5 s** primary criterion (market production-viability ceiling)
and a **`time_to_first_audio` p95 ≤ 1.2 s** engineering sub-target; ~700 ms stays an
aspirational experience target reachable only via speech-to-speech. Prerequisite to
sign-off: instrument true mouth-to-ear (`channel_egress` + end-of-turn hold,
**TASK-WEB-014**). STT/TTS are at the Gradium floor, so the latency lever is the
answer engine and the criterion — not the voice edges; ADR-0012 (modular cascade) is
reaffirmed and "OpenAI" for V1 means the cascade chat provider (ADR-0006/DEC-011),
not Realtime speech-to-speech.

**OQ-005 sub-items — resolved by TASK-WEB-014:**
- **Journeys counted toward the pilot metric:** warm streaming **WebRTC** turns on the
  **web** channel with the **real backend** that produce a complete end-of-turn →
  first-audio path. A turn missing any required slice (e.g. a barge-in turn with no
  final answer) is **excluded**, never counted as a fast turn; fixture-only and
  stub-backend runs are engineering baselines, not pilot-gate inputs.
- **Fixture-vs-live provider mix:** the ADR-0029 gate is measured with **live** Gradium
  STT/TTS + the real backend. Fixture providers are deterministic dev/CI only and never
  feed the gate; `pipeline_timing`'s "first present span name wins" already prevents a
  fixture span and a web span mixing into one slice distribution.
- **Barge-in authority:** the Pipecat **output transport** is authoritative for barge-in
  cancellation timing (emits Bot Started/Stopped-speaking frames, flushes on
  `InterruptionFrame`). Barge-in turns are excluded from `voice_to_first_audio` (no
  complete answer); barge-in is tracked separately via `voice.barge_in.count`, not
  folded into the first-audio composite.

**Owner:** Product / Architecture / Operations  
**Impacts:** EPIC-004, EPIC-005, EPIC-009

### Question

Under which measured conditions is the V1 voice journey accepted for the pilot?

### Why It Matters

ADR-0018 defines `time_to_first_audio` p95 below 800 ms as a pilot criterion in a
pre-warmed, co-located environment, not a production SLO. The backlog must avoid
turning an aspirational target into an unmeasured contractual promise.

### Needed Decision

- Measurement environment and sample size.
- Which journeys count toward the pilot metric.
- Which latency slices must be reported separately: channel ingress,
  end-of-turn, STT, backend first token, BSS/PDF evidence, comparison, RAG,
  LLM, TTS first audio, channel egress, and Genesys handoff.
- Which tests use controlled fixtures, fake providers, sandbox providers, or
  real provider calls.
- Warm and cold conditions: cache state, pre-opened TTS connection, pre-warmed
  LLM, preloaded vector index, and co-location assumptions.
- How long-running BSS evidence analysis is handled with a quick spoken
  acknowledgement.
- What latency or evidence failures require degraded mode or escalation.
- How barge-in is measured and which component is authoritative for cancelling
  playback or interrupting an in-flight turn.

---

## OQ-006 - Genesys Handoff Integration Shape

**Status:** **Strategic direction decided (2026-08-27) — Genesys = full pilot entry** (DEC-012),
**handoff by-reference** (DEC-013); **residual technical/compliance items still open.** The strategic
items are settled: full Genesys Audio Connector voice routing **is** the pilot target (not spike-only),
Genesys **is** the phone entry point for pilot calls, the single pilot entry is **Genesys** (US-018
Twilio/SIP deferred), and the escalation-handoff transport is **`handoff_id` + backend fetch** (inline
Architect-variable context **rejected** on PII/trust-boundary grounds).
**Resolution vehicle for the rest = Sprint 13** (`sprints/sprint-13-genesys-audio-connector.md`):
the **TASK-WEB-025** spike remains the **latency/feasibility gate** (deciding Genesys as the entry does
**not** waive it — a gate-fail escalates to the user, it does not auto-proceed), and **ADR-0049** records
the delivery shape.

**✅ Additionally decided by the user (2026-08-28, DEC-014):**
- **Spike PII posture = synthetic-first** — the TASK-WEB-025 spike runs on **synthetic / non-PII audio
  only**; the real-PII egress sign-off is a **parallel** item (see the residual list), **not** a spike
  blocker.
- **Pilot concurrency target = 3** concurrent Genesys sessions — the spike checks this fits the premium
  **≤5-integrations / 1-vCPU** envelope.
- **Genesys pilot environment is available now** (org + Architect access) — the live-measurement steps
  can be human-run once the throwaway prototype is ready.

**Residual OPEN items** (owners):
- **Codec — PCMU vs L16 end to end** + transcode budget — *spike (TASK-WEB-025)*.
- **15-minute cap fit** vs the worst-case billing journey + mitigation (checkpoint/resume or call-back)
  — *spike (TASK-WEB-025)*.
- **PII-audio residency / egress** from the Genesys cloud to the runtime VMs (region, encryption,
  compliance sign-off) — **user (Security / Compliance)**. **Still OPEN — parallel track, not a spike
  blocker (DEC-014).** Aligned with OQ-009 (production data-protection gate).
- **Pilot concurrency** vs the premium **≤5-integrations / 1-vCPU** envelope — *spike (TASK-WEB-025) +
  product*. **Target set = 3 concurrent sessions (DEC-014); the spike verifies the fit.**

This OQ stays Open until those residual items report and the decision owners sign off.  
**Owner:** Product / Contact Center / Architecture / Security  
**Impacts:** EPIC-006, EPIC-007, EPIC-008, EPIC-009 — Sprint 13

### Question

Which Genesys mechanism and payload shape are required for V1 advisor handoff?

### Why It Matters

Genesys is the V1 escalation target, but the product must distinguish mandatory
advisor handoff from optional full Audio Connector voice routing. The handoff
contract determines what context can be sent to the advisor and what security
constraints apply.

### Needed Decision

- **✅ Decided (DEC-013):** Genesys handoff mechanism for the pilot = **`handoff_id` +
  backend fetch** (by reference); inline Architect-variable context rejected (PII/trust
  boundary).
- **✅ Decided (DEC-013):** required and allowed handoff fields through Genesys are
  limited to the opaque `handoff_id` + minimal routing metadata; the full audited
  `EscalationHandoff` stays backend-owned.
- **⏳ Open (spike):** the exact customer/session identifiers allowed by the pilot trust
  model (which minimal routing metadata rides alongside the `handoff_id`).
- **⏳ Open (spike + infra, TASK-INFRA-012):** queue or skill routing rules for billing
  advisor escalation.
- **✅ Decided (DEC-012):** full Genesys Audio Connector routing **is** required for the
  pilot (pilot target, not spike-only) — the TASK-WEB-025 latency/feasibility gate still
  applies.
- **✅ Decided (DEC-012):** Genesys **is** the phone entry point for pilot calls (not only
  the advisor-handoff target).
- **✅ Decided (DEC-012):** the selected media integration is the **Audio Connector**
  (bidirectional AudioHook); SIP/Twilio as a separate entry (US-018) is deferred.
- **⏳ Open (spike):** which Genesys attributes / task variables carry the minimal routing
  metadata (transcript summary, detected intent, escalation reason, BSS evidence and
  unresolved points are fetched from the backend, not pushed inline).
- **⏳ Open (product):** which Genesys Analytics metrics and AI-layer metrics are combined
  in the pilot KPI dashboard.

---

## OQ-007 - Backend AI/RAG Framework (Spring AI vs LangChain4J vs Other)

**Status:** ✅ Decided (2026-07-17) — **Spring Boot + Spring AI** for V1, recorded in
[ADR-0026](../../docs/architecture/adrs/ADR-0026-backend-runtime-and-ai-framework.md).
Quarkus + LangChain4j deliberately deferred (reconsidered only on an ops/native-image
or complex-agentic trigger). Providers stay behind replaceable ports (DEC-005, DEC-011,
ADR-0006). TASK-BE-001 (Sprint 7) implements the recorded decision.
**Owner:** Architecture / Backend
**Impacts:** EPIC-005, EPIC-006 (TASK-WEB-003-C HTTP backend adapter and the future
Java answer engine that implements the conversation contract), EPIC-002/003/004

### Question

Which framework does the Java backend use to build the answer engine (LLM
orchestration, RAG, tool/function calling, provider abstraction): **Spring AI**,
**LangChain4J**, or another option?

### Why It Matters

The Sprint 5 backend bridge is deliberately **contract-first**: the voice runtime
talks to a `BackendAnswerPort` with a stub adapter (default) and an HTTP adapter,
so **Sprint 5 does not require this decision**. But the real answer engine behind the
HTTP contract does. The choice affects provider replaceability (DEC-005: LLM/STT/TTS
must stay swappable behind ports), RAG/pgvector integration, guardrails, streaming
support, observability hooks (DEC-010) and team familiarity.

### Needed Decision

- Framework for LLM orchestration + RAG in the Java backend.
- How it preserves the provider-agnostic port/adapter boundary (Mistral API default,
  Ollama alternative for chat; Ollama `nomic-embed-text` for embeddings).
- Streaming-token support for the low-latency voice loop (feeds Sprint 6).
- Whether the decision warrants an ADR under `docs/architecture/adrs/`.

### Notes

- Deferred by the user until after Sprint 5 planning; **must not be forgotten** — to
  be discussed before the Java answer engine (HTTP backend behind TASK-WEB-003-C)
  is implemented.

---

## OQ-008 - Retrieval Quality Strategy And Vector Store (pgvector vs Qdrant, hybrid/rerank/scale)

**Status:** Open (raised 2026-07-22 while triaging [BUG-003](../bugs/BUG-003-kb-chunking-brittle-retrieval-handoff.md))
**Owner:** Architecture / Backend
**Impacts:** EPIC-005 (answer engine / knowledge base), ADR-0006, ADR-0007, ADR-0030

### Question

Do we keep **pgvector** (current, one Postgres for `vector_store` + `kb_source_state`
ledger + sessions) and improve retrieval quality on top of it (hybrid dense+sparse
search, reranking, MMR/diversity), or do we move the vector store to **Qdrant**
(native hybrid/sparse vectors, reranking, quantization, horizontal scale) — and if so,
when and behind what trigger?

### Why It Matters

BUG-003 showed the current failure is **not** a vector-store limitation: it is caused by
malformed chunking (mid-word splits, `X \n\n X` duplication, header-only chunks) plus a
dense-only, brittle top-K where keyword-dense header chunks evict the answer chunk.
Switching engines with the same corpus/strategy would reproduce the same failure — so the
question is genuinely "retrieval **strategy**", where the store is only one lever.
pgvector is amply sufficient for V1 volume (~10k chunks) and keeps a single datastore;
Qdrant adds real capabilities but also new infra, a new adapter, a full re-sync, and loses
the "one Postgres" simplicity.

### Needed Decision

- Confirm the lever order: (1) fix chunking, (2) topK/over-fetch + MMR, (3) hybrid
  (keyword + dense, e.g. Postgres FTS `tsvector`), (4) cross-encoder reranker, (5) change
  vector DB — with (5) gated on a concrete trigger. **Lever order confirmed in ADR-0032.**
- Concrete trigger(s) that would justify Qdrant (native hybrid without hand-rolling,
  volumetry ≫ V1, quantization, vector multitenancy, latency at scale).
- Whether hybrid/rerank on pgvector is enough to meet the retrieval-quality bar after
  BUG-003 is fixed (**measure before deciding**).
- Whether the eventual decision warrants a full ADR (stubbed as ADR-0032, Proposed).

### Progress (2026-08-13)

- ✅ Lever 1 (chunking) done via BUG-003; ✅ lever 2 top-K over-fetch done (4 → 8);
  BUG-004 (LLM refusal) closed. MMR / hybrid / rerank not yet built.
- The remaining decision now hinges on **measurement**, not more debate. ADR-0032 adds a
  measurement protocol (labeled FR/EN eval set with phrasing variants; recall@k, MRR,
  phrasing-stability; proposed bar recall@8 ≥ 0.9 & stability ≥ 0.9).
- **TASK-BE-027** built the offline eval harness + labeled eval set (`scripts/retrieval_eval/`);
  **TASK-BE-028** adds MMR gated on the baseline. OQ-008 is resolved once the harness numbers
  show whether pgvector + the needed levers clear the bar or a Qdrant trigger has fired.
- **Baseline (2026-08-13, dense-only, top-K=8; measures whole-pipeline grounding success, not
  isolated vector recall):** overall recall@8 **0.90**, phrasing-stability **0.79**. FR / billing
  / commercial clear the bar (billing & commercial perfect). **Miss classification is decisive:**
  of 3 failures, **2 are `OFF_TOPIC` input-guardrail blocks on EN** (`sup-en-internet`,
  `sup-en-wifi` — retrieval never ran, a BUG-001-class over-block, **not** a retrieval/vector
  problem) and **1 is a genuine retrieval eviction** (`sup-fr-slow`).
- **Corrected lever reading:** no Qdrant trigger; pgvector retrieval is strong. **MMR
  (TASK-BE-028)** was implemented and **A/B-measured on the live corpus (2026-08-13,
  `ab-mmr-2026-08-13.md`)** — result: it does **not** clear the bar and is **left OFF by
  default**. λ=0.7 degrades recall@8 0.90→0.86 / stability 0.79→0.71 (compressed `nomic` scores
  let the diversity term dominate); λ=0.9 is neutral and does not fix the one eviction.
- **Query greeting-normalization (TASK-BE-029)** was then implemented and **A/B-measured
  (2026-08-13, `ab-query-norm-2026-08-13.md`)** to test whether the eviction was greeting-induced —
  result: **strictly neutral, left OFF by default**, and the **greeting hypothesis is disproven**.
  Stripping "Bonjour," leaves `"internet est très lent chez moi."`, which **still** misses the
  answer chunk in top-8, whereas the bare variant `"Ma connexion internet est très lente."` hits it
  at rank 2. So `sup-fr-slow` is a **core-phrasing recall miss**, not a greeting one — neither MMR
  nor greeting normalization reaches it.
- **Corrected next lever = phrasing-robust recall:** hybrid lexical (`tsvector`) + dense fusion or
  query expansion — or enrich the eval set with a variant that differs *only* by the greeting. This
  is the remaining concrete OQ-008 follow-up (query normalization and diversity are both exhausted).
- The **EN gap is guardrail topicality (OFF_TOPIC over-block), out of OQ-008 scope** → tracked as
  **BUG-016** (was informally "BUG-009" before that number went to the Ansible deploy bug;
  unbounded `king`/`roi`/`queen` OFF_TOPIC pattern matched "wor**king**", fixed with word
  boundaries 2026-08-14). EN support **content coverage** is a separate gap for Product. Without
  the guardrail-vs-eviction split this would have been misattributed to retrieval (the BUG-003 trap).

### Notes

- Vector store already sits behind `VectorStorePort` / `VectorSearchPort`, so a future
  swap is feasible without touching the domain.
- Do **not** couple this to BUG-003: BUG-003 is fixed on pgvector (chunking); this OQ is
  the follow-up on retrieval-quality strategy and possible engine change.

---

## OQ-009 - Data Residency And DPA For Cloud AI Processors (Mistral Chat + Gradium STT/TTS)

**Status:** Open (raised 2026-08-15, global-review decision #6) — **external input**
(operator DPO + provider contracts). Framed as a **production gate**, not a pilot blocker
while the pilot runs on non-production / test data.
**Owner:** Product / Legal (operator DPO) + Architecture
**Impacts:** EPIC-009 (trust, security, auditability), ADR-0039 (provider egress), ADR-0006
(Mistral chat), ADR-0023/0024 (Gradium STT/TTS), TASK-BE-031 (data-minimization follow-up)

### Question

Under what data-protection terms may **customer personal data** be sent to the cloud AI
processors, and what residency / retention / training guarantees are required before any
**real** customer traffic? Two egress flows carry personal data off-box:

- **Customer voice audio → Gradium** (STT + TTS), and
- **Customer turn text → Mistral** (chat / wording).

(Embeddings stay local on the VM per ADR-0039 — no RAG egress. The KB is operator content,
not customer PII.)

### Why It Matters

For a Telecom/ISP billing assistant, voice audio and turn text are **personal data** (and can
reveal account, billing and identity details). Sending them to cloud processors without a
signed DPA, an EU/agreed residency guarantee, a no-training assurance and a defined retention
is a **GDPR/compliance exposure**. `infra-v1.md` already flags that a strong sovereignty/residency
constraint would push toward a self-hosted GPU pool; `cahier-des-charges-fonctionnel.md` lists a
GDPR incident category and a configurable session retention, and notes studying self-hosting for
sovereignty. None of this is yet backed by an explicit provider-processing posture.

### Needed Decision (external inputs to obtain)

- **DPA** signed with Mistral and with Gradium (GDPR Art. 28 processor terms), with a
  **sub-processor** list.
- **Data residency**: confirmed processing region (EU) or an explicit accepted deviation.
- **Training opt-out**: written assurance that customer audio/text is **not** used to train
  provider models.
- **Retention**: provider-side retention of submitted audio/text (ideally zero/ephemeral) and
  our own configurable retention aligned with it.
- **Pilot guardrail**: the eir-ai4cc-tst pilot must **not** process real customer PII until the
  above are confirmed — use test personas / synthetic data. This must be stated in the deployment
  doc.
- **If residency is denied**: fall back to the `infra-v1.md` self-hosted GPU lever (sovereign
  STT/TTS/LLM) — larger cost/latency trade-off, decided separately.

### Notes

- Engineering follow-up (what we control now) is tracked as **TASK-BE-031**: a data-processing
  inventory (what personal data goes to which processor), PII redaction before egress where
  feasible, configurable retention, and confirming no raw audio/PII in logs.
- This OQ is about **contractual/residency posture** (external), distinct from the transport
  security of the ops surface (TASK-BE-023) and the egress *reachability* policy (ADR-0039).
