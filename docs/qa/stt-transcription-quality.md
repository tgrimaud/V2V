# STT Transcription Quality Validation (TASK-STT-002)

**Ticket:** TASK-STT-002 - Validate STT transcription quality with audio fixtures
**Related stories:** US-019, US-036
**Branch:** `task/TASK-STT-002-stt-quality-fixtures`
**Harness:** `voice-agent/stt_validation/quality.py` + `voice-agent/fixtures/manifest.json`

## Scope and honesty note

This validates the **quality-evaluation harness and the first controlled fixture
set**, using the deterministic `FixtureSttProvider` (the `.txt` sidecar is the
simulated engine output). It does **not** yet measure a real STT engine — that
depends on provider selection (see the sprint open questions). When a real
provider adapter is connected, the same manifest and harness produce real
quality numbers with zero test changes.

## How quality is scored

- The manifest stores a ground-truth `reference` per fixture.
- The provider returns a hypothesis transcript.
- `word_error_rate(reference, hypothesis)` is a Levenshtein word-level WER.
- `quality_score = max(0, 1 - WER)`; a fixture passes when
  `quality_score >= quality_threshold` (default `0.8`).
- Unusable audio (`expect_usable: false`, e.g. silence) passes only when the
  path reports failure/unavailable and **invents no transcript**.

## QA fixture inventory

| Fixture | Category | Usable? | Reference (ground truth) |
|---|---|---|---|
| `short-greeting` | short | yes | `Bonjour` |
| `long-billing-question` | long | yes | `Pourquoi ma facture de telephone est plus elevee que le mois dernier` |
| `noisy-billing-question` | noisy | yes | `je voudrais comprendre le montant de ma derniere facture mensuelle` |
| `accented-billing-question` | accented | yes | `est-ce que je peux payer ma facture en plusieurs fois` |
| `silence-clip` | silence | no (must not transcribe) | — |

All five declared categories (`short`, `long`, `noisy`, `silence`, `accented`)
are covered. `missing_categories: []`.

## Transcript results (run 2026-07-09)

Command:

```bash
cd voice-agent
python3 -m stt_validation.quality_cli fixtures/manifest.json
```

| Fixture | Category | Outcome | WER | Quality | Pass | Note |
|---|---|---|---|---|---|---|
| short-greeting | short | success | 0.0 | 1.00 | yes | meets threshold |
| long-billing-question | long | success | 0.0 | 1.00 | yes | meets threshold |
| noisy-billing-question | noisy | success | 0.1 | 0.90 | yes | 1 word error, meets threshold |
| accented-billing-question | accented | success | 0.1 | 0.90 | yes | 1 word error, meets threshold |
| silence-clip | silence | failed | — | — | yes | correctly unusable, no transcript invented |

- `ready: true`
- `missing_categories: []`
- `failed_categories: []`
- STT slice latency (`stt_request_ms`): `count=5, p50≈0.023ms, p95≈0.032ms`
  (fixture provider, not a real engine).

## Acceptance criteria coverage

| Acceptance criterion | Covered? | Evidence |
|---|---|---|
| Transcript quality reviewed per fixture category | Yes | per-fixture table + `category` field in report |
| Missing fixture categories explicitly reported | Yes | `missing_categories` list; unit test `test_missing_categories_are_reported_explicitly` |
| Silence/unusable reported as unavailable/failed | Yes | `silence-clip` outcome `failed`, empty transcript |
| No invented transcript accepted as valid | Yes | `test_invented_transcript_for_unusable_audio_fails` |

## Defects

No blocking defects for the current fixture set: all declared categories are
present and all quality gates pass. If a future run produces
`failed_categories` or `missing_categories`, QA must open a bug ticket using
`product-backlog/templates/bug-ticket-template.md` before STT is declared ready.

## Open risks

- Quality numbers reflect the fixture provider, not a real STT engine.
- The first fixture set has one sample per category; more samples are needed
  before p95/p99 and per-category quality are statistically meaningful.
- Real-speech accented and noisy audio may behave very differently from the
  controlled sidecar hypotheses.

## Reproduce

```bash
cd voice-agent
python3 -m unittest discover -s tests -p 'test_*.py'
python3 -m stt_validation.quality_cli fixtures/manifest.json
```
