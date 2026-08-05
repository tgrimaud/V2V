# BUG-007 — Voice `/converse` and `/converse-stream` never apply the KB domain filter

## Header

- **Bug ID:** BUG-007
- **Title:** Primary voice endpoints retrieve across all domains (domain filter not applied)
- **Status:** New
- **Severity:** Medium
- **Priority:** P2
- **Detected by:** Adversarial review
- **Detected date:** 2026-08-05
- **Related user story:** US-034 (RAG answer engine) / EPIC-012
- **Related epic:** EPIC-012
- **Branch:** `fix/BUG-007-converse-domain-filter`
- **Owner:** Backend developer

## Problem Statement

The primary voice conversation endpoints pass `domain=null` into retrieval grounding, so KB
search spans **all** domains instead of scoping to `billing | support | commercial` (plus
`general`). The documented per-domain filtering only takes effect on `/answer` and `/retrieve`.

## Environment

- **Environment:** local / test
- **Channel:** web voice (and text via `/converse`)
- **Provider configuration:** Ollama embeddings + pgvector; Mistral chat
- **Build or commit:** `feat/sprint-11-remote-deployment`
- **Correlation ID:** n/a

## Reproduction Steps

1. Given a KB with chunks tagged `domain=billing`, `domain=commercial`, and `domain=support`.
2. When a question is asked through `POST /api/conversation/converse` (or `/converse-stream`).
3. Then retrieval returns chunks from all domains (subject only to the audience filter), not
   the intended single-domain scope.

## Expected Result

The voice path retrieves within the relevant domain (or an explicitly documented cross-domain
policy), consistent with the domain filtering applied on `/answer` and `/retrieve` and with the
project's documented `domain == X OR general` behaviour.

## Actual Result

`ConversationService` and `StreamingConversationService` call grounding with a `null` domain, so
no domain scoping is applied on the primary voice/text path.

## Evidence

- Test output: n/a (behaviour confirmed by code review)
- API response: n/a
- Code: `backend/src/main/java/com/voicesupport/conversation/application/service/ConversationService.java:40-42`
  (`null` domain) and comment at `:15-16` ("spans all domains"); `StreamingConversationService.java:73`
  (`null` domain). Contrast with the domain-filtered `/answer` and `/retrieve` paths.

## Impact

- **customer impact:** low today (V1 KB is effectively single-domain), but once billing +
  commercial + support content coexist, answers can pull cross-domain chunks → wrong or mixed
  answers.
- **operational impact:** latent correctness/routing risk that will surface exactly when the
  KB grows into multiple domains (the V1 direction).
- **latency/SLO impact:** none.

## Acceptance Criteria For Fix

- [ ] `/converse` and `/converse-stream` apply the domain filter (or the cross-domain choice is
      explicitly documented as intended, with rationale).
- [ ] A regression test asserts the domain filter is applied on the voice path.
- [ ] Relevant OpenTelemetry traces, metrics and structured logs are present or explicitly not
      applicable.
- [ ] Adversarial code review is at least 90% satisfied.
- [ ] QA retest passes.
- [ ] Related documentation or backlog notes are updated if behavior changed.

## Developer Notes

- root cause:
- files changed:
- tests added/updated:
- OpenTelemetry added/updated:
- residual risk:

## QA Retest

- **Retested by:**
- **Retest date:**
- **Scenarios rerun:**
- **Result:**
- **Retest evidence:**

## Closure

- **Closed by:**
- **Closed date:**
- **Closure reason:**
