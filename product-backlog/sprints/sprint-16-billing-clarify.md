# Sprint 16 — Billing Clarification (diagnostic questioning before answering)

## Sprint Objective

Make the bot **understand a billing problem before answering it**. Today a billing turn
goes straight to RAG and the assistant answers directly — users report it as "too direct /
it just enumerates the bill". This sprint adds a short, **bounded clarifying dialogue** so
the assistant asks a few targeted questions first, then gives a more appropriate answer or
escalates with a well-prepared context.

Delivers **US-043** in two increments (delivery order chosen by the user, 2026-10-08):

- **D first — TASK-BE-070** (quick, low risk, deterministic): broaden the existing
  `ProblemOpenerDetector` billing path and turn the targeted clarify into **one short
  question at a time** (voice-friendly, FR/EN). No multi-turn state, no LLM.
- **C target — TASK-BE-071** (builds on D): a deterministic "billing + under-specified"
  trigger + a **clarify counter in conversation memory** (bounded) + a **bounded, natural
  LLM follow-up**. The collected context improves both the grounded answer and the
  ADR-0019 escalation handoff.

## Scope

### In Scope

- US-043 — ask clarifying questions before answering a billing problem (both increments).
- Deterministic trigger + bound (never loops; after the cap, answer or escalate).
- One short clarifying question per turn on the voice channel; FR/EN.
- Observability: clarify-asked, clarify count per conversation, outcome
  (answered-after-clarify vs escalated-after-clarify), cap-hit (mandatory runtime
  instrumentation).

### Out Of Scope

- Any live BSS/invoice lookup or stating customer-specific amounts (target-only on the
  pilot; **DEC-002 unchanged** — a clarifying question never states an unevidenced amount).
  The clarify improves **retrieval relevance + escalation context**, not invoice figures.
- A general-topic intent classifier (billing is the focus; other topics keep today's
  behavior beyond the existing generic opener clarify).
- Changing which documents are retrieved (retrieval scope unchanged).

## Business Rules (traceability → US-043)

| ID | Rule |
|----|------|
| BR1 | An under-specified billing problem triggers a clarifying question, not an immediate enumeration |
| BR2 | One short question per turn (no multi-question lists on voice); never exceed the configured maximum |
| BR3 | After the clarify budget, answer from evidence or offer a human advisor — never loop |
| BR4 | A clarifying question never states an amount/price absent from the evidence (DEC-002) |
| BR5 | Explicit advisor request / off-topic / unsafe / a specific answerable question are not intercepted (guardrail ladder wins) |
| BR6 | Clarify wording follows the session language (FR/EN) |

## Tickets

| # | Ticket | Title | Role | Depends on | Status |
|---|--------|-------|------|-----------|--------|
| 1 | TASK-BE-070 | Increment D — broaden `ProblemOpenerDetector` billing path + one-question-at-a-time clarify (deterministic, no LLM) | Backend (guardrails) | — | 🟢 Open (deliver first) |
| 2 | TASK-BE-071 | Increment C — deterministic trigger + clarify counter in memory (bounded) + bounded LLM follow-up; collected context → answer + ADR-0019 escalation | Backend (flow + prompt) | TASK-BE-070 | 🟢 Open (after D) |

Full ticket detail: `tasks/task-be-070-billing-clarify-one-question-at-a-time.md`,
`tasks/task-be-071-billing-diagnostic-bounded-llm-followup.md`.

## Definition of Done (per ticket)

- Behavior matches US-043 ACs; deterministic trigger + bound enforced server-side (not
  prompt-trust).
- DEC-002 preserved on clarify turns (no unevidenced amount) — locked by a regression test.
- Backend `mvn test` green (ArchUnit + hexagonal + unit); pure domain stays Spring-free;
  beans wired in `DomainServiceConfig`. Manual fakes, GIVEN/WHEN/THEN, no Mockito.
- Clarify/outcome telemetry present and asserted.
- Adversarial code review ≥ 90% before QA acceptance, persisted to
  `docs/qa/<ticket>-adversarial-review.md` + a pointer line in the ticket.
- Docs updated with the change (clarify behavior + any new config key).
- Merge only on the user's explicit request (ticket → sprint via `git merge --no-ff`).

## Open Questions

| OQ | Question | Owner | Status |
|----|----------|-------|--------|
| OQ-043-a | Max clarifying questions on voice (1/2/3) before answering/escalating | Product | Open — default assumption 2 (needed for C / TASK-BE-071, not D) |
| OQ-043-b | Should the billing sub-types offered be configurable per deployment | Product | Open |
| OQ-043-c | Does the multi-turn diagnostic (C) change the conversation contract enough to need an ADR | Architecture | Open — decide before TASK-BE-071 implementation |

## Observability & Latency

- Clarify turns are short LLM turns with minimal/no retrieval; measure the clarify turn as
  its own slice and confirm no voice-SLO regression.
- Correlation id carried as usual; clarify metrics (above) satisfy US-043 analytics so QA
  can verify the bound.

## Sprint Branch

`feat/sprint-16-billing-clarify`, forked from `feat/restart-from-scratch` (2026-10-08).
Ticket branches (`task/TASK-BE-070-*`, `task/TASK-BE-071-*`) fork from and merge back into
this sprint branch (`git merge --no-ff`); the sprint branch merges into
`feat/restart-from-scratch` only at closure on the user's explicit request (two-level model).

## Traceability

- **User story:** US-043 (`stories/v1-user-stories.md`).
- **Tickets:** TASK-BE-070 (D), TASK-BE-071 (C).
- **EPICs:** EPIC-005 (answer engine) / EPIC-006 (web voice journey).
- **Decisions/ADRs:** DEC-002 (grounding — LLM phrases only), BUG-025
  (`ProblemOpenerDetector` + targeted clarify), ADR-0034 (audience boundary),
  TASK-BE-018 (voice concision), ADR-0019 (escalation handoff). Possible new ADR per OQ-043-c.

## Status

🟡 **In progress (opened 2026-10-08)** — sprint branch created; US-043 + TASK-BE-070/071
tickets drafted. No implementation started yet. TASK-BE-070 (increment D) is next.
