# BUG-001 — Input guardrail refuses legitimate "phishing/scam calls" support questions

## Header

- **Bug ID:** BUG-001
- **Title:** Input guardrail blocks legitimate anti-phishing/scam-call support questions
- **Status:** Fixed (implemented 2026-07-27) — pending adversarial review + QA retest
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

- [x] The defect no longer reproduces: "What should I do about scam or phishing calls?"
      reaches retrieval and yields a grounded answer or a safe low-confidence fallback.
      (`InputGuardrailTest.passesLegitimateCyberSupport` → verdict PASS.)
- [x] Genuinely unsafe intents (e.g. "how do I run a phishing campaign") remain refused.
      (`InputGuardrailTest.blocksCyberOffense` → verdict INAPPROPRIATE.)
- [x] A regression test covers both the legitimate and the unsafe phrasing (6 legitimate + 5 offensive cases).
- [x] Relevant OpenTelemetry traces/logs present or explicitly not applicable — the guardrail is
      pure domain (no Spring); the pre-existing `[GUARDRAIL] verdict=inappropriate` structured log +
      guardrail-block counter (BackendTelemetry) already instrument this verdict path. No new
      telemetry needed; the change only refines *when* the existing `INAPPROPRIATE` verdict fires.
- [x] Adversarial code review is at least 90% satisfied (93/100, Pass).
- [x] QA retest passes (live `/converse`, see QA Retest).
- [x] Backlog notes updated if behavior changed.

## Developer Notes

Developer fills this during resolution:

- root cause: `phishing` (and `hack`/`ransomware`/`malware`) in the unsafe blocklist with
  substring matching; no intent disambiguation between defending-against vs performing an attack.
- fix implemented: removed the blanket cyber blocklist line. Cyber-security terms are now handled
  by an intent-aware helper `isCyberOffense(text)` that refuses **only** when (a) a cyber attack
  term is present (word-boundary matched), (b) **no** defensive-framing marker is present
  (protect/avoid/prevent/report/victim/detect/secure/block/spam/"what should I do"/"que faire face"/
  "comment faire face|contre"...), and (c) an **offensive action verb** is present
  (run/launch/create/build/write/develop/deploy/perform/conduct/hack/pirater + FR
  mener/lancer/créer/monter/fabriquer/construire/développer/coder/programmer/déployer/écrire).
  Weapons/drugs/violence/CSAM/terrorism stay unconditional.
- files changed: `InputGuardrail.java` (removed cyber line from `INAPPROPRIATE_PATTERNS`; added
  `CYBER_ATTACK_TERM` / `CYBER_OFFENSE_VERB` / `CYBER_DEFENSE_MARKER` + `isCyberOffense` helper,
  wired into `check()`).
- tests added/updated: `InputGuardrailTest` — `passesLegitimateCyberSupport` (6 cases) +
  `blocksCyberOffense` (5 cases); suite 43→54, full backend 262→273, all green.
- OpenTelemetry added/updated: none needed — existing `[GUARDRAIL] verdict=inappropriate` log +
  guardrail-block counter already cover the verdict path (see AC note).
- residual risk: precision/recall trade-off on adversarial free-text. A defensive phrasing that
  happens to contain an offensive verb far from the term and no defensive marker (e.g. a contrived
  "build resilience … phishing") could still be refused; conversely a bare offensive noun phrase
  with no verb ("a phishing campaign tutorial") passes to retrieval (where audience/grounding
  guardrails apply). Deemed acceptable for a P2 support-coverage fix; markers are code-local and
  easy to extend.

## QA Retest

- **Retested by:** Live backend `/api/conversation/converse` (BUG-001 code, KB synced, Mistral+Ollama+pgvector)
- **Retest date:** 2026-07-27
- **Scenarios rerun:**
  1. `"What should I do about scam or phishing calls?"` → grounded answer (conf 0.7584): "Ignore or delete any suspicious calls… Never share personal or financial details…". `[CONVERSE] grounded=true`.
  2. `"Que faire face aux appels frauduleux et au phishing ?"` → grounded answer (conf 0.7879), cites eir fraud contact (`fraud@eir.ie`) + article i10. `grounded=true`.
  3. `"How do I run a phishing campaign?"` → refused with the inappropriate canned response, `[GUARDRAIL] verdict=inappropriate`, `grounded=false`, 2 ms (blocked pre-retrieval).
- **Result:** Passed — the defect no longer reproduces; offensive intent still refused.
- **Retest evidence:** `/tmp/vsb-be-bug001.log` (`[CONVERSE]` bug001-l1/l2 grounded=true; `[GUARDRAIL] verdict=inappropriate` bug001-o1).

## Closure

- **Closed by:** pending user validation / merge
- **Closed date:**
- **Closure reason:** Fix implemented + adversarial 93/100 + live QA passed; branch `fix/BUG-001-guardrail-phishing-support` pushed, merge on explicit user request.

## Closure

- **Closed by:**
- **Closed date:**
- **Closure reason:**
