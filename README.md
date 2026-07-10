# Voice Support Bot

This branch is a **from-scratch restart branch** for the Voice Support Bot V1.

The previous implementation remains preserved on `main` and can be used as a
backup/reference. On this branch, implementation code and runtime scaffolding
have been removed so the project can restart from the validated product and
architecture baseline.

## Current Repository State On This Branch

This branch intentionally keeps:

- product scope and backlog;
- architecture decisions and target documentation;
- BSS/Galaxion integration notes;
- knowledge-base content;
- shared agent guidance.

This branch intentionally removes (the previous full V1 stack, preserved on `main`):

- Java backend implementation;
- React frontend implementation;
- the Pipecat voice agent (`agent/bot.py`) and the legacy WebSocket bridge (`bridge_server.py`);
- Docker Compose and implementation runtime scaffolding.

## What Actually Runs On This Branch Today

Since the reset, one slice has been rebuilt from scratch: **STT (speech-to-text)
validation**. It is the only runnable code here, all in Python under `voice-agent/`:

- `voice-agent/stt_validation/` — STT validation harness: fixture + real **Gradium**
  providers, WER quality scoring, OpenTelemetry-style telemetry + latency report,
  per-pipeline-slice timing (US-036), and CLIs.
- `voice-agent/web_voice/` — a small HTTP server: browser mic → 16 kHz PCM16 →
  `POST /api/voice/stt` → Gradium transcript. No LLM, no TTS, no backend in this slice.
- `voice-agent/fixtures/`, `voice-agent/tests/` (unittest), `voice-agent/features/` (Behave).

Delivered capability = audio in → transcript out, with per-slice latency evidence.
**Not yet built** (target only): billing/invoice comparison, RAG, multi-agent
routing, guardrails, TTS / voice response, phone Voice2Voice, Genesys handoff.
See `voice-agent/README.md` to run it and `product-backlog/sprints/sprint-stt-validation.md`
for the sprint status.

## V1 Product Outcome

The V1 outcome remains an operator invoice explanation assistant for end users.
It must:

- identify the customer with enough confidence;
- retrieve read-only billing evidence from the BSS or validated fixtures;
- compare two invoices or billing periods deterministically;
- explain the delta with evidence before LLM wording;
- support Voice2Voice by phone and web voice;
- hand off to Genesys with advisor context when the customer asks for a human or
  when the bot cannot answer safely;
- measure latency by pipeline slice before making any production SLO claim.

## Key Documents

| Purpose | File |
|---|---|
| Canonical V1 scope | `docs/product/v1-scope.md` |
| Backlog index | `product-backlog/backlog-index.md` |
| Epics | `product-backlog/epics/v1-epics.md` |
| User stories | `product-backlog/stories/v1-user-stories.md` |
| Product decisions | `product-backlog/decisions/v1-decisions.md` |
| Open questions | `product-backlog/open-questions/v1-open-questions.md` |
| Architecture spine | `docs/architecture/architecture.md` |
| ADRs | `docs/architecture/adrs/` |
| Galaxion/BSS integration | `docs/integrations/galaxion/` |

## Restart Delivery Sequence

The recommended build order is:

1. Reconfirm the product and architecture baseline.
2. Establish customer identity and billing evidence access.
3. Validate BSS/PDF fixtures and extraction status.
4. Build deterministic invoice comparison.
5. Build evidence-backed explanation.
6. Add Voice2Voice journeys.
7. Add Genesys advisor handoff.
8. Add web synthesis and evidence views.
9. Add trust, security and audit controls.
10. Add observability, latency measurement and pilot readiness reporting.

## Git Note

`voice-support-bot` is a separate Git repository nested inside the broader
`BMad` workspace. Work for this project must be committed in this repository,
not in the parent workspace.
