# Adversarial Review — Documentation & Architecture (pre-sprint cleanliness gate)

- **Date:** 2026-08-28
- **Branch:** `feat/sprint-12-external-voice-websocket` (read-only review; no branch switch, no file edits other than this report)
- **Reviewer skill set:** `adversarial-architecture-review` (NFR/SLO scorecard, provider replaceability, Genesys/omnichannel readiness) + `technical-writer` (English-only, doc quality) + `software-architect` (ADR discipline, layer rules)
- **Goal:** Confirm the docs (`docs/`) and product backlog (`product-backlog/`) are clean and internally consistent before Sprint 13 opens: ID integrity, status coherence, docs-vs-code drift, English-only, broken links, and an adversarial pass on the Sprint 13 (Genesys) architecture shape.

---

## Scope

- **`docs/`** — architecture spine (`architecture.md`, `infra-v1.md`), ADRs (`docs/architecture/adrs/`, 46 files ADR-0001…0045 + ADR-0048), diagrams, reviews, QA reports, `operations/development-workflow.md`, integrations (Galaxion), product (`v1-scope.md`, cahier).
- **`product-backlog/`** — `backlog-index.md` registry, EPICs, user stories, tasks, `decisions/v1-decisions.md`, `open-questions/v1-open-questions.md`, `sprints/`, templates, `review-findings.md`, `done-tasks.md`.
- **Root** — `README`/`CLAUDE.md`/`AGENTS.md` consistency with the actual `backend/` + `voice-agent/` code.

## Method

- **ID integrity:** grep for `ADR-`, `TASK-`, `US-`, `BUG-`, `DEC-`, `OQ-`, `RF-` id patterns; check for duplicates within the branch, dangling references, and registry-vs-file agreement.
- **Status coherence:** cross-read status of the flagged tickets (`TASK-STT-014`, `TASK-BE-020`, `TASK-BE-033/034/035`, `ADR-0029` gate) across `backlog-index.md`, ticket-detail task files, sprint files, and `done-tasks.md`.
- **Docs-vs-code drift:** confirm documented REST routes, the BUG-007 null-domain cross-domain contract, the Mistral(chat)/Ollama(embedding) split, and the KB sync endpoints against `backend/src/main/java`.
- **English-only:** heuristic French-word scan under `docs/`, then manual triage of hits.
- **Architecture adversarial pass:** stress-test the Sprint 13 Genesys shape (ADR-0040 Audio Connector + ADR-0042 no-TURN + ADR-0043 interim WS) against NFR/SLO, degraded modes, escalation contract, provider replaceability, PII-audio residency (OQ-009), and the ADR-0029 latency-gate blocking dependency.

> **Note on the review brief vs. actual artifacts.** The brief referenced
> `sprints/sprint-13-genesys-audio-connector.md` and "ADR-0049 Genesys Audio
> Connector". **Neither exists on this branch.** There is no Sprint 13 file (only a
> tentative registry row), and the Genesys Audio Connector decision is **ADR-0040**
> (with ADR-0042 no-TURN and ADR-0043 interim WebSocket), not ADR-0049 (which does not
> exist). The review adapted to the artifacts actually present. See Finding B-1 / M-4.

---

## Overall score: 82 / 100

The corpus is unusually disciplined: no duplicate IDs within the branch, honest
built-vs-target framing, API docs that match code byte-for-byte on the routes checked,
and the two most sensitive statuses (TASK-STT-014 rejected, ADR-0029 gate FAIL)
consistent everywhere. The deductions are concentrated in **staleness on the active
sprint branch** (three registries lag the delivered work) and **one genuine status
contradiction**, plus a **merge-time ID-collision risk** created by branching 23 commits
behind mainline.

## Verdict: **NOT-CLEAN (conditional) for Sprint 13**

Not a redesign problem — every finding below is a fast documentation edit. But two
materially stale registries + one contradictory status + an ADR/TASK numbering gap that
will collide at merge should be reconciled **before** Sprint 13 allocates new
`ADR-00xx` / `TASK-BE-0xx` ids off this branch, or the collision risk compounds.

---

## ID & status integrity (explicit subsection)

**No within-branch collisions found.** Zero duplicate `ADR-####` headings, zero
duplicate `TASK-*` registry rows, zero duplicate `US-###`; `OQ-001…009` match between
`backlog-index.md` and `v1-open-questions.md`. The Sprint 13 collision the brief warned
about (`TASK-BE-034/035/036/037`, `ADR-0048/0049`) is **not present**: `TASK-BE-036`,
`TASK-BE-037`, `ADR-0046`, `ADR-0047`, `ADR-0049` do **not** exist anywhere on this
branch, and `TASK-BE-034/035` + `ADR-0048` are each defined exactly once.

**Contradictions / gaps found:**

| # | Type | Detail | Where |
|---|---|---|---|
| C-1 | **Status contradiction** | `TASK-BE-020` = "🟢 Implemented + merged into sprint 12 + live-measured (2026-08-27)" in the detail file, but "To do (future improvement, out of Sprint 10)" in the registry. | `product-backlog/tasks/backend-hardening-tasks.md:821-823` vs `product-backlog/backlog-index.md:130` |
| C-2 | **Stale registry** | Sprint-12 ticket table shows all 7 tickets `📋 Planned` and header `🚧 In progress`, but `backlog-index.md` records TASK-WEB-026…030 **merged** and WEB-031 **functional-GO/latency-FAIL**. The file also omits the extra scope actually delivered on the branch (BE-020, STT-014, WEB-032/035/036, BE-033, OPS-009, BE-034/035, ADR-0045/0048). | `product-backlog/sprints/sprint-12-external-voice-websocket.md:71-77` |
| C-3 | **Stale built-vs-target note** | ADR README "built vs target" note (dated 2026-08-05, "Sprint 11 branch") lists **ADR-0043 as "Accepted, scheduled — not built yet"**, but ADR-0043 is **built + merged** on this branch. ADR-0040/0042/0044/0045/0048 are not categorized in the note at all. | `docs/architecture/adrs/README.md:9-30` |
| C-4 | **ADR numbering gap / merge-collision risk** | ADR files jump `0045 → 0048`; `ADR-0046`/`0047` are absent on this branch but referenced as reserved on mainline. `done-tasks.md:1081` states this branch is "behind mainline by ~23 commits … a later merge reconciles with ADR-0046/0047." ADR-0048 + TASK-BE-034/035 were allocated on the behind-branch → **collision risk at merge** if mainline already used those ids. | `docs/architecture/adrs/README.md`, `done-tasks.md:1081` |
| G-1 | **Missing brief artifacts** | `sprint-13-genesys-audio-connector.md` and "ADR-0049" (per the brief) do not exist. No **broken internal link** results (the registry row for Sprint 13 is text-only, unlinked), so this is a brief-vs-repo mismatch, not a repo defect. | `product-backlog/sprints/` |
| D-1 | **Absent-by-design** | `DEC-012`/`DEC-013` do not exist and are referenced nowhere; the decisions table ends at DEC-011. The 2026-08-15 "global-review decision #1…#9" is a **separate** numbering scheme (loop decisions, not `DEC-###`). No broken reference, but two "decision" numberings coexist. | `product-backlog/decisions/v1-decisions.md`, `backlog-index.md` |

---

## Blockers

**B-1 — ADR/TASK id allocation on a branch 23 commits behind mainline (C-4).**
Because `ADR-0046`/`0047` already exist on `feat/restart-from-scratch` and this branch
skipped them to create `ADR-0048`, and because `TASK-BE-034/035` were minted here too,
a Sprint 13 that allocates the next "free" number **off this branch** can double-allocate
an id already used on mainline. This is the one finding that can cause real, silent
breakage (two different decisions sharing one number after merge).

- **Fix:** before Sprint 13 opens, either (a) merge this branch's additive doc rows into
  mainline and re-number any true collision (`ADR-0048` → next free after mainline's
  head; `TASK-BE-034/035` likewise), or (b) allocate all new Sprint 13 ids from
  mainline's ADR/TASK head, not this branch's. Record the reconciliation in
  `done-tasks.md`. Ref: `docs/architecture/adrs/README.md`, `done-tasks.md:1081`.

*(Everything else below is a Major/Minor doc edit, not a blocker.)*

---

## Majors

**M-1 — TASK-BE-020 status contradiction (C-1).** Registry says "To do", detail file
says "Implemented + merged into sprint 12". A reader planning Sprint 13 latency work
cannot tell whether Lever B's prerequisite is done.
- **Fix:** update `backlog-index.md:130` to the merged/live-measured status (matching
  `backend-hardening-tasks.md:821-823` and the QA report
  `docs/qa/task-be-020-first-sentence-latency-report.md`), preserving the "ADR-0029 gate
  still FAIL, model-dominated → TASK-BE-033" caveat.

**M-2 — Sprint-12 file materially stale (C-2).** The sprint file is the sprint's
source of record; showing merged tickets as `📋 Planned` and omitting ~10 delivered
items misrepresents the branch state at the exact moment Sprint 13 is being scoped from it.
- **Fix:** refresh the ticket table statuses to match `backlog-index.md`, and add the
  out-of-original-plan scope actually landed on the branch (BE-020, STT-014 rejected,
  WEB-032/035/036, BE-033, OPS-009, BE-034/035, ADR-0045/0048) either as rows or a
  "Scope added during the sprint" note. File: `sprint-12-external-voice-websocket.md:71-77`.

**M-3 — ADR README built-vs-target note stale (C-3).** It tells readers ADR-0043 is not
built (false on this branch) and omits ADR-0040/0042/0044/0045/0048 from the
built/target/proposed buckets.
- **Fix:** re-date the note to the Sprint 12 branch; move ADR-0043 to **Built**; add
  ADR-0042/0044 to **Built (pilot decisions)**, ADR-0040 to **Target-only (Sprint 13,
  gated OQ-006)**, ADR-0045 to **Proposed**, ADR-0048 to **Built/Accepted (pilot FR
  corpus)**. File: `docs/architecture/adrs/README.md:9-30`.

**M-4 — ADR index numbering gap unexplained (C-4).** The index jumps 0045→0048 with no
note that 0046/0047 are reserved-on-mainline. A reader will read it as a lost ADR.
- **Fix:** add a one-line note in `docs/architecture/adrs/README.md` that 0046/0047 live
  on mainline and are pending reconciliation at merge (tie to B-1).

---

## Minors (typos / style / ordering)

- **m-1 — Bug table row order.** `BUG-016` (`backlog-index.md:285`) is listed **before**
  `BUG-015` (`:286`). Cosmetic; reorder for scan-ability.
- **m-2 — Dual "decision" numbering (D-1).** `DEC-001…011` vs "global-review decision
  #1…#9" can confuse. Consider renaming the loop items ("global-review item #n") or
  cross-noting the distinction where they first appear.
- **m-3 — Brief-vs-repo mismatch (G-1).** The review brief cited a non-existent
  `sprint-13-genesys-audio-connector.md` and "ADR-0049". When Sprint 13 opens, create the
  sprint file and (correctly) reference **ADR-0040/0042/0043** for the media plane; do not
  mint an "ADR-0049 Genesys Audio Connector" (ADR-0040 already owns that decision).
- **m-4 — English-only: PASS with caveat.** The French-word heuristic flagged ~10 docs,
  but every hit is a **quoted example** (FR closing phrases in ADR-0035, FR/EN corpus
  discussion in ADR-0031/0048, French test transcripts in QA reports, JSON examples in
  `voice-runtime-http-contract.md`). No doc is authored in French prose → compliant with
  the technical-writer English-only rule. No fix required.

---

## Docs-vs-code drift check (spot audit) — PASS

| Claim | Doc source | Code reality | Verdict |
|---|---|---|---|
| Answer routes `converse`, `converse-stream`, `answer`, `retrieve`, `warm-up` under `/api/conversation` | CLAUDE.md, voice-runtime-http-contract | `ConverseController`, `ConverseStreamController` (SSE, `text/event-stream`), `AnswerController`, `RetrievalController`, `WarmUpController` all `@RequestMapping("/api/conversation")` | ✅ Match |
| KB sync endpoints `POST /api/knowledge/sync` + `/sync/{sourceType}` + `/ingest` | CLAUDE.md, KB guide | `KnowledgeController` `@PostMapping("/sync")`, `/sync/{sourceType}`, `/ingest` | ✅ Match |
| BUG-007 null-domain cross-domain retrieval (voice path spans all domains, by design) | CLAUDE.md, BUG-007, OQ-008 | `ConversationService` passes `domain=null` with an explicit BUG-007 comment block | ✅ Match |
| LLM = Mistral (chat, default), Embedding = Ollama `nomic-embed-text` 768 | ADR-0006, DEC-011, CLAUDE.md | `application.yml`: `provider: ${LLM_PROVIDER:mistral-api}`, embeddings `nomic-embed-text`, comment "Embeddings always stay on Ollama" | ✅ Match |
| TASK-STT-014 = Rejected (measured harmful) | backlog-index, QA report, done-tasks, tasks file, ADR-0029/0037 | Runtime code reverted per done-tasks 2026-08-27; QA header "❌ REJECTED" | ✅ Consistent everywhere |
| ADR-0029 latency gate = FAIL (m2e p95 > 1.5 s) | backlog-index, sprint-10/11/12, WEB-031/032, full reviews | Consistent FAIL narrative (p95 ≈ 2142 ms after levers; WS 3675 / WebRTC 3743 ms warm) | ✅ Consistent |

No stale API claims found in the spot audit.

---

## Architecture adversarial pass — Sprint 13 Genesys shape (ADR-0040 / 0042 / 0043)

**Verdict: the docs honestly represent "solid MVP, not yet industrialized" — proceed to
Sprint 13 only as a bounded, measured spike (matches ADR-0020 + TASK-WEB-025 posture).**
The existing `genesys-audio-connector-adversarial-review-2026-08-07.md` already scores the
target 2.2/5 with risks R1–R6, and the 2026-08-05 full review scores the whole app ≈2.6/5.
This review affirms that framing and adds nothing that contradicts it.

| Dimension | /5 | Rationale (docs-grounded) |
|---|---:|---|
| NFR / SLA fitness | 2 | ADR-0029 gate already **FAIL** on the shortest WebRTC path (m2e p95 ≈ 2.1 s live, WS 3.7 s). A Genesys cloud round-trip + PCMU/L16 transcode + extra `wss` hop can only add latency; the Genesys leg is **unmeasured**. Correctly gated (OQ-006, spike TASK-WEB-025). |
| SLA failure modes | 2 | Endpoint-down / session-drop / 15-min cap mid-call / transcode failure have **no designed degraded mode** yet (documented as R2/R3). The Architect "resume flow at session end" hook is a natural fallback but unspecified. |
| Modularity & boundaries | 3–4 | Strongest axis: clean 3-plane split (media / control / context), backend keeps the brain (RAG, guardrails, escalation, memory). Genesys sits behind the ADR-0009 channel envelope. `EscalationHandoff` → Architect-variable mapping is **unproven** (R5). |
| Provider replaceability | 3 | Brain **Easy** (in-house, behind `LlmPort`/`BackendAnswerPort`); media plane **Hard** (bespoke Genesys `wss` AudioHook server, premium, ≤5 integrations/org, 1 stream/session). ADR-0043 session-factory + PCM16 boundary + pluggable control-signal seam are the right hedges and are **built** in Sprint 12. |
| Evolvability / industrialization | 2 | Premium + concurrency-capped provider, LB VMs 1 vCPU, no per-leg SLO decomposition, no load test for this path. A spike, not a brick. |

**PII-audio residency (open item, honestly tracked).** OQ-009 (customer audio → Gradium,
turn text → Mistral) is **Open**, framed as a **production gate** (signed DPA + EU
residency + training opt-out + retention/sub-processors) with engineering follow-up
TASK-BE-031; embeddings already local (ADR-0039). Genesys audio adds a further processor
to that inventory — the docs should extend OQ-009's processing inventory to the Genesys
media leg when Sprint 13 opens (recommend, not a defect today).

**Latency-gate blocking dependency.** The docs are internally honest that ADR-0029 is FAIL
and that Genesys starts "in deficit" (R1). The correct sequencing — land Lever B
(TASK-BE-033 / ADR-0045) and re-score the direct path **before** adding the Genesys leg —
is already implied but is **not stated as an explicit Sprint 13 entry gate**. Recommend
Sprint 13 add an explicit precondition: "direct-path m2e re-scored post-Lever-B; Genesys
leg measured in isolation (TASK-WEB-025) before any routing commitment."

---

## Residual risk

- **Merge reconciliation (B-1)** is the only item that can cause silent breakage; until
  the branch is merged and ids are reconciled, treat `ADR-0048` / `TASK-BE-034/035` as
  provisional numbers.
- The stale registries (M-2, M-3) are low-risk while the sprint is in-flight but must be
  refreshed at Sprint 12 closure (the two-level branch model requires the sprint file +
  backlog-index + done-tasks to agree at closure — a fast-forward carries no closure
  commit, so nothing self-updates).
- The Genesys architecture risk is **accepted and gated** (OQ-006, spike-only); no residual
  beyond re-scoring latency and closing OQ-009 before any real-customer Genesys traffic.

---

## Recommended fix order (all fast doc edits)

1. **B-1 / M-4** — reconcile ADR/TASK numbering vs mainline before Sprint 13 allocates ids.
2. **M-1** — fix the TASK-BE-020 registry status (contradiction).
3. **M-2 / M-3** — refresh the Sprint 12 file + ADR built-vs-target note (do at sprint closure at the latest).
4. **m-1 / m-2 / m-3** — cosmetic (bug row order, decision-numbering note, create the real Sprint 13 file citing ADR-0040/0042/0043 when the sprint opens).
