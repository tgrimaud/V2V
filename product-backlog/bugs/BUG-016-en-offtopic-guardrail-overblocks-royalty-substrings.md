# BUG-016 — EN OFF_TOPIC guardrail over-blocks royalty substrings (`king` in "working")

## Header

- **Bug ID:** BUG-016
- **Title:** Input guardrail OFF_TOPIC royalty pattern lacks word boundaries — over-blocks legitimate EN support turns
- **Status:** ✅ Fixed on `feat/sprint-11-remote-deployment` (global adversarial review remediation, 2026-08-14) — pending user validation
- **Severity:** Medium
- **Priority:** P2
- **Detected by:** Retrieval A/B evaluation (2026-08-13) + global adversarial review (2026-08-14)
- **Detected date:** 2026-08-13
- **Related user story:** EPIC-005 (Answer engine / knowledge base); ADR-0014 / ADR-0034 guardrails
- **Related epic:** EPIC-005
- **Branch:** `feat/sprint-11-remote-deployment`
- **Owner:** Backend developer

> **Numbering note.** This bug was informally referred to as "BUG-009" in
> `docs/architecture/adrs/ADR-0032`, `product-backlog/open-questions/v1-open-questions.md`
> and `scripts/retrieval_eval/reports/ab-mmr-2026-08-13.md`, but BUG-009 was later
> assigned to the Ansible LB re-enable deploy bug. This ticket gives the guardrail
> over-block its own number (BUG-016); those references were repointed here.

## Problem Statement

The pre-retrieval input guardrail (`InputGuardrail`) classifies a turn as `OFF_TOPIC`
using a list of regex patterns. The royalty pattern listed the bare tokens
`roi|queen|king` with **no word boundaries** and matched with `Matcher.find()`
(substring, anywhere). As a result `king` matched inside common English support
words — **wor**king****, **boo**king****, **loo**king****, **par**king**** — and
`roi` inside **ad**roi**t**. Those legitimate EN support turns were refused with the
canned off-topic message **before retrieval ever ran**, which showed up as the EN
recall/stability gap in the 2026-08-13 A/B eval (EN recall@4 0.50, stability 0.33;
the two EN misses were guardrail blocks, not retrieval evictions). This is the same
substring-over-block class as BUG-001 (and the documented `ip` ⊂ `équipement` trap).

## Fix

`InputGuardrail.OFF_TOPIC_PATTERNS` now bounds the royalty tokens
(`\broi\b|\bqueen\b|\bking\b`). `président`/`capitale`/`capital of` are unchanged.
A genuine royalty question ("Who is the king of England?") is still blocked; EN
support turns containing `working`/`booking`/`looking`/`parking` now reach retrieval.

## Acceptance Criteria

- [x] EN support turns containing `working`/`booking`/`looking`/`parking` are **not**
      OFF_TOPIC-blocked.
- [x] A genuine royalty/off-topic question ("Who is the king of England?") is still
      blocked as OFF_TOPIC.
- [x] Regression tests added in `InputGuardrailTest`
      (`passes_en_support_turns_that_contain_royalty_substrings`,
      `still_blocks_a_genuine_royalty_question`).
- [x] `mvn -o test` green.
- [ ] Live EN retest confirms the EN recall/stability gap narrows (out of OQ-008
      retrieval scope; guardrail fix only).
