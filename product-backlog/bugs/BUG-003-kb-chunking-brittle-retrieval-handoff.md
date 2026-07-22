# BUG-003 — Over-fragmented KB chunking makes retrieval brittle → LLM hand-off → "not enough info" on covered topics

## Header

- **Bug ID:** BUG-003
- **Title:** Legitimate, KB-covered questions (technical support, résiliation) fall back to "Je n'ai pas assez d'informations fiables…" because the chunk holding the real answer is evicted from top-K
- **Status:** New
- **Severity:** High
- **Priority:** P1
- **Detected by:** User validation (live WebRTC test)
- **Detected date:** 2026-07-22
- **Related user story:** US-042 (UI language selector — surfaced during its live test)
- **Related epic:** EPIC-005 (Answer engine / knowledge base)
- **Branch:** `fix/BUG-003-kb-chunking-brittle-retrieval`
- **Owner:** Backend developer

## Problem Statement

On the voice path, many legitimate questions whose answer **is present in the knowledge base**
(e.g. "j'ai un problème de connexion internet", "j'ai un problème avec ma box") are answered with
the canned low-confidence fallback ("Je n'ai pas assez d'informations fiables pour répondre à
cette question. Souhaitez-vous que je vous mette en relation avec un conseiller ?") instead of the
troubleshooting steps that exist in the KB. The failure is **unstable**: the same question can
succeed or fail depending on a trivial phrasing change (adding "Bonjour,"). Reproduces in **French
and English**.

## Environment

- **Environment:** local
- **Channel:** web voice (WebRTC, `stt_mode=streaming`) — also reproduced backend-only via
  `POST /api/conversation/converse` and `/api/conversation/retrieve`
- **Provider configuration:** LLM `mistral-api` (`mistral-small-latest`), embeddings Ollama
  `nomic-embed-text` (768d); Postgres pgvector (**10 166 chunks**, ingested from `articles-fr.csv`
  ~2.2 MB)
- **Build or commit:** `us/US-042-ui-language-selector` @ `9ee7685`
- **Correlation IDs:** `c84b99aa-…` (fail), `90d2f91f-…` / `747162aa-…` (success)

## Reproduction Steps

1. Given the voice server up (`web_voice.server --provider gradium --backend http`,
   `VOICE_DEBUG_TRANSCRIPT=1`) and the backend on `:8080` with the `articles-fr.csv` corpus loaded.
2. When the customer says (voice or `/converse`) **"Bonjour, j'ai un problème de connexion
   internet."**
3. Then the bot replies with the low-confidence fallback — even though the KB contains a
   "Ma box ne se connecte plus à Internet" article with explicit steps.
4. When the customer says the **same question without the greeting** ("J'ai un problème de connexion
   internet."), the bot answers correctly ("Redémarrez votre box… câble Ethernet…").

## Expected Result

A question whose answer exists in the KB is answered from that content. The outcome must not flip
on trivial phrasing (greeting prefix) and must be language-independent (FR/EN).

## Actual Result

Live turns captured (`VOICE_DEBUG_TRANSCRIPT`, `/tmp/vsb-voice.log`), transcripts are **clean**
(no STT error):

| Transcript (STT correct) | Result |
|---|---|
| "Bonjour, j'ai un problème de connexion internet." | ❌ low-confidence fallback |
| "Bonjour, j'ai un problème avec ma box." | ❌ low-confidence fallback |
| "J'ai un problème de connexion internet." (no greeting) | ✅ answered (redémarrer box…) |
| "Je souhaiterais résilier mon abonnement." | ✅ answered |

English (via `/converse`, `language=en`) — same class of failure:

| EN transcript | Result |
|---|---|
| "I have an internet connection problem." | ✅ conf 0.72 |
| "I have a problem with my box." | ❌ "I don't have enough reliable information…" |
| "My internet connection is not working." | ❌ blocked off-topic |

## Evidence

- **Retrieval passes but returns unusable chunks.** `/api/conversation/retrieve` for "Bonjour,
  j'ai un problème de connexion internet." (top_k=4):

  | hit | score | contains steps? | text head |
  |---|---|---|---|
  | 0 | 0.862 | no | `# Base de connaissance — Support Telecom FAI \n ## Problèmes de connexio…` (header-only, 123 chars) |
  | 1 | 0.829 | no | `mi ou dans une résidence secondaire), mais cela \n\n ami ou dans une rés…` (self-duplicated fragment) |
  | 2 | 0.823 | no | `ant que **IDS avec rendez-vous**. --- \n\n tant que **IDS avec…` (mid-word start, duplicated) |
  | 3 | 0.812 | no | `-- **Que faire en cas de problème avec ma connex \n\n --- **Que faire…` (duplicated) |

  The chunk that actually holds the answer (681 chars: "### Ma box ne se connecte plus à Internet
  1. Vérifiez que tous les câbles… 2. Redémarrez la box…", itself starting mid-word "ernet") is
  **not in the top-4**.

- **Malformed chunks in `vector_store`:** headers isolated into their own chunk (123 chars, no
  body), chunks split mid-word (`ernet`, `ami`, `ant que`), and text **duplicated inside a single
  chunk** (`X \n\n X` pattern) → over-fragmentation to **10 166 chunks** (was ~5 177 before the
  `articles-fr.csv` re-ingestion, cf. BUG-002).

- **Top-4 scores are near-identical (0.862 / 0.829 / 0.823 / 0.812)** → the ranking is unstable;
  adding "Bonjour," reorders the top-4 and evicts the answer chunk, flipping the outcome.

## Impact

- **Customer impact:** the bot fails to answer questions it *does* have content for, on both the
  billing/résiliation and technical-support domains, and behaves inconsistently for the same intent.
  This is the core value proposition failing on the voice pilot.
- **Perceived as a voice/WebRTC bug** but is channel- and language-independent (reproduced
  backend-only in FR and EN). Misleads triage.
- **Pilot-readiness impact:** blocks a credible voice demo; retrieval quality/SLO claims are not
  defensible with this corpus.
- No security/privacy impact.

## Root Cause (preliminary)

RAG ingestion/chunking quality, not WebRTC/STT and not the retrieval confidence threshold:

1. The `articles-fr.csv` ingestion produces **over-fragmented, mid-word-split, internally
   duplicated** chunks (the `X \n\n X` pattern points to a broken chunk-overlap implementation),
   and Markdown **headers become their own keyword-dense chunks with no body**.
2. On a topical query the content-less header chunk ranks #1 and the duplicated fragments fill the
   rest of top-K, **evicting the chunk that holds the real answer** (steps). Because top-K scores
   are within ~0.05 of each other, ranking is brittle → trivial phrasing changes flip the result.
3. The LLM, given only headers/fragments, follows its directive and **hands off** ("…je vous
   transfère à un conseiller"). `OutputGuardrail.isNonAnswer()` detects the hand-off marker and
   **rewrites it into the low-confidence message** — so a retrieval/corpus problem surfaces as
   "not enough info", and grounded answers never happen even though grounding was `answerable=true`.

Note: lowering `voice-support.conversation.confidence-threshold` (0.5) does **not** help — the
retrieval guardrail already passes (0.86); the block is downstream (LLM hand-off → output guardrail).

## Acceptance Criteria For Fix

- [ ] The KB is re-ingested with a correct chunker: no mid-word splits, no internal duplication
      (`X \n\n X`), Markdown sections kept with their heading + body, no header-only chunks.
- [ ] For "problème de connexion internet" / "ma box", the top-K contains the chunk with the actual
      steps and the bot answers with them — **with or without** a greeting prefix.
- [ ] The outcome is stable to trivial phrasing changes (greeting prefix) and reproduces neither in
      FR nor EN.
- [ ] Total chunk count for `articles-fr.csv` is sane (no ~2× inflation from overlap duplication).
- [ ] A regression test covers "covered technical question → grounded answer" (sync + streaming),
      and a retrieval-quality check asserts the answer chunk is in top-K.
- [ ] Relevant OpenTelemetry (retrieval hits/scores, grounded flag) present or N/A.
- [ ] Adversarial code review ≥ 90 %.
- [ ] QA retest passes (unit + live voice).
- [ ] Docs/backlog updated if the chunking strategy changes (KB ingestion notes / ADR if needed).

## Developer Notes

Developer fills this during resolution:

- root cause: (confirm the chunk-overlap duplication and header-isolation in the CSV connector /
  `TextChunker`; inspect how `articles-fr.csv` is ingested vs the Markdown connector)
- files changed:
- tests added/updated:
- OpenTelemetry added/updated:
- residual risk:

Suggested direction: fix the chunker (correct overlap, keep heading with body, drop empty/header-only
chunks, avoid mid-word cuts), re-ingest `articles-fr.csv` cleanly, and consider raising
`voice-support.conversation.retrieval.top-k` 4 → ~8 as defense-in-depth. Separately, review whether
the LLM should compose from partial evidence rather than hand off so eagerly (careful with DEC-002 —
that constraint is about *amounts*, not troubleshooting steps). The off-topic block on "My internet
connection is not working." is a distinct guardrail concern — track separately if confirmed.

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
