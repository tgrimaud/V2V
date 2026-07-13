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

**Update (TASK-STT-007, 2026-07-10):** the fixture set is now **22 real raw PCM16
mono 16 kHz clips** (`fixtures/generate_fixtures.py`, macOS `say`) — **5 samples per
usable category** (short, long, noisy, accented) with varied voices/phrasings, plus
2 silence clips. Each clip is padded with 300 ms lead-in / 200 ms lead-out silence
so Gradium's endpointing does not clip the first word. The report now aggregates
**per-category** quality + latency and flags categories below the reporting floor
(`MIN_SAMPLES_FOR_PERCENTILES = 5`) as not yet significant. See the
**"Expanded fixture set" section below** for the current per-category numbers; the
5-fixture tables further down are kept as the earlier historical snapshots.
Caveats (unchanged): `say` speech is clean/synthetic, `noisy` mixes synthetic white
noise, and `accented` uses Canadian-French voices (fr_CA) — proxies, **not**
real-world recordings. Real human samples (especially for `noisy` and ultra-short
`short` clips, which `say` still clips) remain the highest-value follow-up.

## How quality is scored

- The manifest stores a ground-truth `reference` per fixture.
- The provider returns a hypothesis transcript.
- `word_error_rate(reference, hypothesis)` is a Levenshtein word-level WER.
- `quality_score = max(0, 1 - WER)`; a fixture passes when
  `quality_score >= quality_threshold` (default `0.8`).
- Unusable audio (`expect_usable: false`, e.g. silence) passes only when the
  path reports the dedicated `unavailable` outcome (TASK-STT-006) and **invents
  no transcript**.

## QA fixture inventory (expanded, TASK-STT-007)

The manifest (`voice-agent/fixtures/manifest.json`) declares **22 fixtures** across
all five categories. The full reference text lives in the manifest; the per-category
breakdown is:

| Category | Usable? | Samples | Voices used | Notes |
|---|---|---|---|---|
| short | yes | 5 | Thomas, Jacques, Flo, Sandy, Rocko (fr_FR) | 1–4 word utterances |
| long | yes | 5 | Thomas, Jacques, Eddy, Flo, Sandy (fr_FR) | full support/billing sentences |
| noisy | yes | 5 | Jacques, Thomas, Flo, Rocko, Sandy (fr_FR) + synthetic white noise | hardest category |
| accented | yes | 5 | Amélie, Eddy, Flo, Reed, Sandy (fr_CA) | genuine fr_CA accent |
| silence | no (must not transcribe) | 2 | — | 1.00 s + 1.50 s zeros |

All five declared categories are covered (`missing_categories: []`). `silence`
(2 samples) is below the reporting floor of 5, but as an *unusable* category (no
WER) it is excluded from the significance aggregate rather than reported as
underpowered — so `underpowered_categories: []` and
`all_categories_significant: true` once every usable category has ≥ 5 samples
(RF-011).

## Expanded fixture set — live Gradium per-category run (TASK-STT-007, 2026-07-10)

Command (normalized WER from TASK-STT-011 is applied):

```bash
cd voice-agent
python3 fixtures/generate_fixtures.py           # 22 clips, padded onsets
export GRADIUM_API_KEY=...                       # from the local .env
python3 -m stt_validation.quality_cli fixtures/manifest.json --provider gradium
```

### Per-category summary

| Category | Samples | Pass | Mean WER | Worst WER | p50 latency | p95 latency | Significant (n ≥ 5) |
|---|---:|---:|---:|---:|---:|---:|---|
| short | 5 | 2/5 | 0.280 | 0.500 | 1474 ms | 1636 ms | yes |
| long | 5 | 2/5 | 0.191 | 0.375 | 2964 ms | 3150 ms | yes |
| noisy | 5 | 1/5 | 0.383 | 0.667 | 2268 ms | 2433 ms | yes |
| accented | 5 | 4/5 | 0.149 | 0.444 | 1985 ms | 2396 ms | yes |
| silence | 2 | 2/2 | — | — | 1123 ms | 1328 ms | **no** (n < 5) |

- `ready: false`; `failed_categories: [accented, long, noisy, short]`;
  `underpowered_categories: []` (silence is unusable → excluded, RF-011);
  `missing_categories: []`.
- **Overall STT slice latency (22 samples):** `min 1123 ms, p50 2165 ms,
  p95 3063 ms, p99 = max 3150 ms`. Latency scales with utterance length (batch STT).

### Interpretation — what is real vs. a synthetic-fixture artifact

The expanded set is deliberately honest: it does **not** pass the gate, and that is
the point — it shows exactly where synthetic `say` fixtures are and are not
representative.

- **`accented` (fr_CA) transcribes well** — 4/5, mean WER 0.149. Two clips are WER
  0.0 (`Est-ce que je peux payer…`, `Je veux ajouter une option…`). Gradium handles
  the Canadian-French voices cleanly.
- **`long` failures are genuine engine errors**, not artifacts: `résilier` →
  `résigner`, `échéancier` → `essai en cire`, `des frais` → `de frais`. The onset
  padding fixed the previously-clipped leading words (`Pourquoi ma facture…` is now
  WER 0.0, was 1.00 before TASK-STT-011 + padding).
- **`short` is dominated by a synthetic artifact:** Gradium's endpointing still
  clips the first word of ultra-short 2–3 word `say` clips even with 300 ms of
  lead-in silence (`Merci beaucoup` → `beaucoup`, `C'est assez urgent` →
  `assez urgent`). On a 2-word reference that single drop is WER 0.5. This is a
  **fixture limitation**, not a Gradium accuracy result — real human recordings with
  natural onsets are needed.
- **`noisy` is genuinely degraded** by the synthetic white noise (`Mon forfait
  mobile a été modifié` → `Mon portrait est mobile, arrêtez de modifier`; one clip
  returns empty). Synthetic noise is a harsh, unrealistic proxy; real ambient-noise
  recordings would behave differently.

### Statistical significance

`MIN_SAMPLES_FOR_PERCENTILES = 5` is a **pragmatic reporting floor**, not a
guarantee of tight percentiles: with nearest-rank percentiles, p95 over 5 samples is
effectively the max. Stable p95/p99 realistically needs many more samples **and**
real human recordings (especially for `noisy`/`short`). The usable categories clear
the floor (flagged significant); `silence` (2) is flagged not significant. Treat the
current per-category WER as **indicative**, not a certified gate.

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

## Live Gradium per-category run (2026-07-10)

First real-engine run over the committed PCM16 fixtures:

```bash
cd voice-agent
export GRADIUM_API_KEY=...   # from the local .env, never committed
python3 -m stt_validation.quality_cli fixtures/manifest.json --provider gradium
```

| Fixture | Reference | Gradium transcript | WER | Quality | Pass |
|---|---|---|---:|---:|---|
| short-greeting | `Bonjour` | `Bonjour.` | 1.00 | 0.00 | no |
| long-billing-question | `Pourquoi ma facture de telephone est plus elevee que le mois dernier` | `ma facture de téléphone est plus élevée que le mois dernier.` | 0.33 | 0.67 | no |
| noisy-billing-question | `je voudrais comprendre le montant de ma derniere facture mensuelle` | `Avec Wottand, le montant de ma dernière facture mensuelle.` | 0.50 | 0.50 | no |
| accented-billing-question | `est-ce que je peux payer ma facture en plusieurs fois` | `que je peux payer ma facture en plusieurs fois ?` | 0.20 | 0.80 | yes |
| silence-clip | — | (empty) | — | — | yes |

- `ready: false`; `failed_categories: [long, noisy, short]`; `missing_categories: []`.
- **Real STT slice latency:** `count=5, min=1093ms, p50=1811ms, p95=p99=2268ms, max=2268ms`.
- Silence correctly returns no speech (`stt_error` / "recognized no speech"), no
  invented transcript.

### Interpretation — the low scores are mostly scoring artifacts, not STT errors

The transcription is largely correct; the failing gate is driven by the WER metric
and by synthetic-fixture limitations, **not** by Gradium accuracy:

1. **Punctuation/case not normalized:** `Bonjour` vs `Bonjour.` scores WER **1.0**
   although the transcript is perfect. The WER is a raw whitespace word-diff.
2. **Accents:** references are ASCII (`telephone`, `elevee`) but Gradium returns
   correct accents (`téléphone`, `élevée`) — counted as word errors.
3. **Leading word clipped:** `Pourquoi`, `est-ce`, `je voudrais comprendre` are
   dropped — the `say`-generated clips start abruptly and truncate the first word.
4. **Only genuine engine degradation:** `noisy` (`Avec Wottand` hallucination),
   caused by the synthetic white noise, not a realistic sample.

**Conclusion:** Gradium performs well; the `ready` gate is not usable against a
real engine until the WER is normalized (see **RF-008 / TASK-STT-011**) and the
fixtures use real recordings with clean onsets (rest of **TASK-STT-007**).

## Normalized WER re-run (TASK-STT-011, 2026-07-10)

After adding transcript normalization (`normalize_transcript`: lowercase, strip
punctuation, fold accents, collapse whitespace — applied identically to reference
and hypothesis before WER), the live Gradium run was repeated. The scores now
reflect real transcription accuracy, not formatting:

| Fixture | Reference | Gradium transcript | WER | Quality | Pass |
|---|---|---|---:|---:|---|
| short-greeting | `Bonjour` | `Bonjour.` | **0.00** | 1.00 | yes |
| long-billing-question | `Pourquoi ma facture de telephone est plus elevee que le mois dernier` | `ma facture de téléphone est plus élevée que le mois dernier.` | **0.083** | 0.917 | yes |
| noisy-billing-question | `je voudrais comprendre le montant de ma derniere facture mensuelle` | `vous le fais conforme le montant de ma dernière facture mensuelle.` | **0.40** | 0.60 | no |
| accented-billing-question | `est-ce que je peux payer ma facture en plusieurs fois` | `que je peux payer ma facture en plusieurs fois ?` | **0.182** | 0.818 | yes |
| silence-clip | — | (empty) | — | — | yes |

- `ready: false`; `failed_categories: [noisy]`; `missing_categories: []`.
- Real STT slice latency: `count=5, min≈1078ms, p50≈1780ms, p95=p99≈2252ms`.
- **`short` went from WER 1.00 → 0.00** (the `Bonjour` vs `Bonjour.` artifact is
  gone); `long`/`accented` now score real, small errors (a clipped leading word).
- **The only remaining failure is `noisy` (WER 0.40) — a genuine transcription
  error** caused by the synthetic white-noise fixture, not a scoring artifact. This
  is the expected behaviour of a meaningful gate and is tied to fixture realism
  (rest of **TASK-STT-007**: real human noisy recording).
- **Threshold decision:** the default `quality_threshold = 0.8` is kept. Once the
  formatting artifacts are removed, 0.8 cleanly separates good transcripts
  (short/long/accented ≥ 0.82) from the genuinely degraded noisy sample (0.60).

**Conclusion (updated):** RF-008 is resolved — the WER gate is now usable against
the real engine. Gradium transcribes the clean/accented samples well; the residual
`noisy` failure is a real fixture-quality issue owned by TASK-STT-007, not a
scoring defect. Note Gradium is non-deterministic on the noisy clip (successive
runs yield different hallucinations, e.g. `Avec Wottand` vs `vous le fais conforme`).

## Acceptance criteria coverage

| Acceptance criterion | Covered? | Evidence |
|---|---|---|
| Transcript quality reviewed per fixture category | Yes | `category_summaries` in the report + per-category table above |
| Each category has multiple fixtures | Yes | 5 samples per usable category (`test_committed_manifest_has_multiple_samples_per_usable_category`) |
| Per-category quality + latency percentiles reported | Yes | `CategorySummary` (mean/worst WER + `LatencyReport` per category) |
| Categories below the required sample size flagged | Yes | `underpowered_categories()` flags any *usable* category with < `MIN_SAMPLES_FOR_PERCENTILES` (5); unusable categories excluded (RF-011) |
| Missing fixture categories explicitly reported | Yes | `missing_categories` list; unit test `test_missing_categories_are_reported_explicitly` |
| Silence/unusable reported as unavailable | Yes | `silence-clip` outcome `unavailable` (TASK-STT-006), empty transcript |
| No invented transcript accepted as valid | Yes | `test_invented_transcript_for_unusable_audio_fails` |

## Defects

No harness defects. Against the real engine the expanded set does **not** pass the
gate (`failed_categories: [accented, long, noisy, short]`), which is the honest,
expected state for synthetic proxies — not a code defect. The `noisy` and ultra-short
`short` failures are fixture-realism issues (synthetic noise; `say` onset clipping);
the `long`/`accented` misses are genuine engine errors on harder vocabulary. STT is
therefore **not certified pilot-ready on quality** until real human recordings are
added. If the *harness* itself regresses (missing categories, invented transcripts on
silence), open a bug ticket via `product-backlog/templates/bug-ticket-template.md`.

## Open risks

- `say` still clips the first word of ultra-short (2–3 word) clips even with 300 ms
  of lead-in silence — the `short` category WER is not representative. **Real human
  recordings are required** for short utterances.
- `noisy` (synthetic white noise) and `accented` (fr_CA `say` voices) are proxies;
  real human noisy/accented recordings may behave very differently.
- 5 samples per usable category clears the reporting floor but is **not** enough for
  stable p95/p99 (nearest-rank p95 of 5 ≈ max). More samples + real recordings needed.

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
