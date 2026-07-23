# Backend Java — Code Quality And Specification Adequacy Review (2026-07-23)

Scope: `backend/` (86 main files / 57 test files), branch `fix/BUG-003-kb-chunking-brittle-retrieval`.
Method: `adversarial-code-review`, `code-guidelines`, `java-backend-developer`, `software-architect` skills.
Reviewer: developer-led adversarial review requested by the user before starting BUG-004.

## Verdict

- **Code quality: Proceed.** The implemented foundation (RAG answer engine + web Voice2Voice loop)
  is clean, tested and industrializable.
- **V1 billing value: not yet built.** The headline V1 value (explaining invoice discrepancies via
  read-only BSS + PDF extraction + deterministic comparison) is absent. This is a **planned and
  accepted** state per ADR-0017 (billing value on a general-support foundation), not a defect — but
  it must be stated plainly: the product promise is not yet deliverable.

## Satisfaction Score

- **Implemented-code quality: 90/100** — QA gate: Pass.
- **V1 "billing" scope adequacy: ~35%** — foundation present, business value planned but absent.

## Implemented vs Specified

| EPIC (spec) | Backend state | Evidence |
|---|---|---|
| EPIC-001 Architecture baseline | Done | Hexagonal, 2 bounded contexts, ArchUnit green |
| EPIC-002 Identity + BSS evidence access | Absent | No `bss`/`identity` code |
| EPIC-003 BSS/PDF extraction | Absent | No `InvoicePdfExtractor` |
| EPIC-004 Deterministic invoice comparison | Absent | No billing package |
| EPIC-005 Evidence-backed explanation engine | Partial | RAG over KB (no BSS deltas): `AnswerService`, guardrails |
| EPIC-006 Voice2Voice foundation | Done | `/converse`, `/converse-stream` (SSE), memory |
| EPIC-007 Genesys advisor handoff | Absent | Only "advisor" wording |
| EPIC-009 Trust/Security/Audit | Minimal | Optional api-key, sanitized errors, no identity/audit |
| EPIC-010 Observability/latency | Partial | Micrometer p50/95/99 + correlated logs — **no OTel spans/exporter** |
| EPIC-011 Multi-agent routing | Absent on this branch | Present on `main` |

A `billing|invoice|bss|escalat|genesys|handoff` search matches only comments/messages, never
business code. The backend today = **general support/RAG + voice**, consistent with ADR-0017.

## Strengths (keep)

- **Clean hexagonal architecture:** pure domain (0 Spring imports in `*/domain`, ArchUnit-enforced),
  `@Bean` wiring per context (`ConversationConfig`, `KnowledgeConfig` — ADR-0027).
- **All classes ≤ 200 lines** (max 151), short methods, controlled nesting — meets `code-guidelines`.
- **Strong test discipline:** 0 Mockito, 0 `@SpringBootTest` (fakes → fast suite, no DB/Ollama),
  6 Cucumber features, 218 tests green.
- **Runtime robustness:** bounded pools (LLM `SynchronousQueue` + `AbortPolicy`, bounded SSE pool),
  LLM timeout + backstop → sanitized **503** degradation (`AbstractChatClientAnswerAdapter`,
  `GlobalExceptionHandler`).
- **Output security:** generic errors + `correlation_id`, never echoes `ex.getMessage()`; telemetry
  is PII-safe (no transcript/answer in logs/tags), `channel` tag cardinality bounded.
- **Replaceable providers:** abstract `AnswerGeneratorPort` (Mistral/Ollama interchangeable);
  embeddings locked to Ollama (768d) via auto-config exclusions.

## Blocking Findings (already ticketed)

| Severity | Finding | Evidence | Action |
|---|---|---|---|
| High | LLM non-deterministically refuses despite grounded evidence | `OutputGuardrail` + `AnswerLanguage` directive | BUG-004 (open) |
| Medium | `InputGuardrail` blocks legitimate anti-phishing/scam support | `INAPPROPRIATE_PATTERNS` contains `phishing|hack` | BUG-001 (open) |

## Non-Blocking Findings (adequacy & maintainability)

| Severity | Finding | Evidence | Recommendation |
|---|---|---|---|
| Medium | No real OpenTelemetry (spans/exporter) vs repo OTel mandate | `pom.xml` (no tracing bridge); `BackendTelemetry` = metrics + logs | Accepted/deferred by ADR-0028. Add the Micrometer→OTel bridge before any prod SLO claim |
| Low | `pom.xml` targets Java 17 vs skill stating Java 21 | `<java.version>17` | Resolved 2026-07-23: Java 17 is the decision (ADR-0026); skill aligned to 17 |
| Low | Regex guardrails are brittle (off-topic false positives, e.g. `qui est…`) | `InputGuardrail.OFF_TOPIC_PATTERNS` | Consider semantic classification (ties into retrieval OQ) |
| Low | `top-k` code default (4) differed from yml (8) | `ConversationConfig` vs `application.yml` | Resolved 2026-07-23: code default aligned to 8 |
| Low | REST endpoints use verbs (`/converse`,`/answer`,`/retrieve`,`/ingest`,`/sync`) vs "no verbs" | REST controllers | Acceptable (RPC voice contract, ADR-0021) — document the accepted deviation |
| Low | Conversation responses not wrapped in `ApiResponse<T>` | `ConverseResponse` | Intentional lean voice contract — pin it in ADR-0021 |
| Info | Fallback answers are stored in conversation memory → prime later turns | `ConversationService.append(...)` | Factor into the BUG-004 fix |

## Observability & Latency

- Present: `voice_support.slice` (slice/channel/provider/outcome, p50/95/99), `prompt_chars`,
  `answer_language`, LLM first-token vs total, end-to-end `correlation_id`, structured logs
  (`[TELEMETRY]/[PROMPT]/[LANGUAGE]/[CONVERSE]`).
- Missing: distributed spans + OTel exporter (bounded to local Micrometer). Risk: no cross-component
  correlation (Genesys↔voice↔backend↔BSS) required by the repo for a credible pilot SLO.

## Security & Privacy

- Good: no upstream error leakage, PII-free logs, no BSS writes.
- Gap: authentication limited to an optional `x-api-key` (empty = open in pilot); no customer
  identity, no audit trail (EPIC-009) — acceptable for pilot, insufficient for production.

## Required / Recommended Actions (prioritized)

1. BUG-004 (open): harden the prompt + lower temperature to stabilize grounded answers.
2. BUG-001 (open): separate legitimate anti-scam help from "how to hack" refusals.
3. Decide OTel: wire the tracing bridge (ADR-0028) or explicitly record the deferral before any SLO.
4. (Done 2026-07-23) Align Java reference to 17; align `top-k` code default to 8.
5. Sequence the V1 value: plan EPIC-002→004 (BSS/PDF/comparison) — the unmet product promise.

## Residual Risk If Accepted As-Is

The foundation is deliverable and QA-ready for a voice support/RAG POC, but: (a) the "invoice"
business value is absent, (b) observability is not distributed → no defensible pilot SLO, (c) the
non-deterministic LLM refusal (BUG-004) degrades perceived experience even when retrieval is good.
