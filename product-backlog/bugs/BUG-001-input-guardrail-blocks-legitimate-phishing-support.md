# BUG-001 — Input guardrail refuses legitimate "phishing/scam calls" support questions

## Header

- **Bug ID:** BUG-001
- **Title:** Input guardrail blocks legitimate anti-phishing/scam-call support questions
- **Status:** New
- **Severity:** Medium
- **Priority:** P2
- **Detected by:** User validation (live test during Sprint 8)
- **Detected date:** 2026-07-21
- **Related user story:** Answer-engine input guardrail (Sprint 7, ADR-0014)
- **Related epic:** EPIC-005 (Answer engine / knowledge base)
- **Branch:** `fix/BUG-001-guardrail-phishing-support`
- **Owner:** Backend developer

## Problem Statement

A customer asking how to deal with scam/phishing calls (a legitimate telecom support
topic that exists in the KB) is refused with the "unsafe request" canned response
instead of getting a grounded answer.

## Environment

- **Environment:** local
- **Channel:** backend-only (`POST /api/conversation/converse`), also affects web/phone voice
- **Provider configuration:** Mistral (LLM) + Ollama (embeddings) + pgvector; full Eir corpus (306 articles) ingested
- **Build or commit:** `fb8a644` (branch `task/TASK-BE-014-batch-embedding`)
- **Correlation ID:** n/a (rejected pre-retrieval)

## Reproduction Steps

1. Given the full Eir KB is ingested (a "Scam Calls and Phishing Attempts" support article exists).
2. When the customer asks: `What should I do about scam or phishing calls?`
3. Then the bot returns: "I cannot help with this type of request. I am a customer support
   assistant..." in ~0.0 s (rejected by the input guardrail before retrieval).

## Expected Result

The question is a legitimate support request. The bot should retrieve the relevant support
article and answer how to recognize/handle scam & phishing calls (or safe fallback if no
evidence), not refuse it as an unsafe/inappropriate request.

## Actual Result

The input guardrail classifies the question as **inappropriate/unsafe** and returns the
canned refusal, skipping retrieval and the LLM entirely.

## Evidence

- Root cause (analysis): `InputGuardrail.INAPPROPRIATE_PATTERNS` contains
  `compile("(hack(er|ing)?|pirater|phishing|ransomware|malware)")`. The token **`phishing`**
  is in the "unsafe request" blocklist and is matched with `Matcher.find()` (substring), so
  any question mentioning phishing — including "how to protect against phishing" — is refused.
  The blocklist does not distinguish *performing* an attack (unsafe) from *defending against*
  it (legitimate support).
- File: `backend/src/main/java/com/voicesupport/conversation/domain/service/InputGuardrail.java`
- Live: `converse` returned the `inappropriate` fallback in ~0.0 s for the question above.

## Impact

- **Customer impact:** legitimate security/support questions (phishing, scam calls) are
  refused — poor experience and a coverage gap for a real telecom support topic.
- **Operational impact:** low for V1 (billing-focused), but the same substring blocklist
  could over-refuse billing-adjacent phrasings; worth fixing before the support domain opens.
- **Security/privacy impact:** none (over-blocking, not under-blocking).
- **Latency/SLO impact:** none.

## Acceptance Criteria For Fix

- [ ] The defect no longer reproduces: "What should I do about scam or phishing calls?"
      reaches retrieval and yields a grounded answer or a safe low-confidence fallback.
- [ ] Genuinely unsafe intents (e.g. "how do I run a phishing campaign") remain refused.
- [ ] A regression test covers both the legitimate and the unsafe phrasing.
- [ ] Relevant OpenTelemetry traces/logs present or explicitly not applicable.
- [ ] Adversarial code review is at least 90% satisfied.
- [ ] QA retest passes.
- [ ] Backlog notes updated if behavior changed.

## Developer Notes

Developer fills this during resolution:

- root cause: `phishing` (and possibly `hack`) in the unsafe blocklist with substring matching;
  no intent disambiguation between defending-against vs performing an attack.
- candidate fix directions (to confirm at fix time): remove `phishing` from the unsafe
  blocklist (it is a legitimate support topic) and/or gate unsafe security terms behind an
  action verb (make/run/perform/create + attack), and use word-boundary matching.
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
