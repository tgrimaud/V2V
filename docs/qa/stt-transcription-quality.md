# STT Transcription Quality Validation (TASK-STT-002)

**Ticket:** TASK-STT-002 - Validate STT transcription quality with audio fixtures
**Related stories:** US-019, US-036
**Branch:** `task/TASK-STT-002-stt-quality-fixtures`
**Harness:** `voice-agent/stt_validation/quality.py` + `voice-agent/fixtures/manifest.json`

## Scope and honesty note

This validates the **quality-evaluation harness and the first controlled fixture
set**. The quality table below is produced with the deterministic
`FixtureSttProvider` (the `.txt` sidecar is the simulated engine output), so those
WER numbers are **not** a real-engine measurement.

**Update (TASK-STT-007, 2026-07-10):** the five category fixtures are now **real
raw PCM16 mono 16 kHz audio** (`fixtures/generate_fixtures.py`, macOS `say`), not
the previous ASCII placeholders. A per-category **Gradium** run is therefore now
possible and only needs a `GRADIUM_API_KEY`:
`python3 -m stt_validation.quality_cli fixtures/manifest.json --provider gradium`.
Caveats: `say` speech is clean/synthetic, `noisy` mixes synthetic white noise, and
`accented` uses a Canadian-French voice (fr_CA) — proxies, not real-world
recordings; real human samples per category remain part of TASK-STT-007.

## How quality is scored

- The manifest stores a ground-truth `reference` per fixture.
- The provider returns a hypothesis transcript.
- `word_error_rate(reference, hypothesis)` is a Levenshtein word-level WER.
- `quality_score = max(0, 1 - WER)`; a fixture passes when
  `quality_score >= quality_threshold` (default `0.8`).
- Unusable audio (`expect_usable: false`, e.g. silence) passes only when the
  path reports failure/unavailable and **invents no transcript**.

## QA fixture inventory

| Fixture | Category | Usable? | Audio (raw PCM16 16 kHz) | Reference (ground truth) |
|---|---|---|---|---|
| `short-greeting` | short | yes | `short/greeting.pcm` (Thomas fr_FR, 0.74 s) | `Bonjour` |
| `long-billing-question` | long | yes | `long/billing-question.pcm` (Thomas fr_FR, 3.50 s) | `Pourquoi ma facture de telephone est plus elevee que le mois dernier` |
| `noisy-billing-question` | noisy | yes | `noisy/noisy-question.pcm` (Jacques fr_FR + white noise, 3.45 s) | `je voudrais comprendre le montant de ma derniere facture mensuelle` |
| `accented-billing-question` | accented | yes | `accented/accented-question.pcm` (Amélie fr_CA, 2.41 s) | `est-ce que je peux payer ma facture en plusieurs fois` |
| `silence-clip` | silence | no (must not transcribe) | `silence/silence.pcm` (1.00 s zeros) | — |

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

- The quality table above reflects the fixture provider, not a real STT engine.
  A real per-category Gradium run is now possible (audio is real) but needs a key.
- One sample per category; more samples are needed before p95/p99 and per-category
  quality are statistically meaningful (rest of TASK-STT-007).
- `noisy` (synthetic white noise) and `accented` (fr_CA `say` voice) are proxies;
  real human noisy/accented recordings may behave very differently.

## Reproduce

```bash
cd voice-agent
# (re)generate the raw PCM16 16 kHz fixtures (macOS `say`)
python3 fixtures/generate_fixtures.py
python3 -m unittest discover -s tests -p 'test_*.py'
# fixture-provider quality (simulated):
python3 -m stt_validation.quality_cli fixtures/manifest.json
# real-engine per-category quality (needs a key):
export GRADIUM_API_KEY=...
python3 -m stt_validation.quality_cli fixtures/manifest.json --provider gradium
```
