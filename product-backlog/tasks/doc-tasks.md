# Documentation Technical Tasks

Cross-cutting documentation reconciliation tasks. Documentation under `docs/` must
be written in English (see `.cursor/skills/technical-writer/SKILL.md`).

| Task | Trigger | Status |
|---|---|---|
| TASK-DOC-001 | Full-branch code review after Sprint 5 | Done (2026-07-15) — tracked in `backlog-index.md` |
| TASK-DOC-002 | Full adversarial code+doc review after Sprint 9 | ✅ Done (2026-07-28) — merged into `feat/restart-from-scratch` |
| TASK-DOC-006 | Clarify Genesys AudioHook vs Audio Connector as the V2V media plane | 🚧 In progress (branch `task/TASK-DOC-006-genesys-audio-connector-media-plane`) |

---

## TASK-DOC-006 - Clarify Genesys AudioHook vs Audio Connector As The V2V Media Plane

**Parent:** EPIC-001 (Product and architecture baseline)
**Related decisions:** ADR-0020 (Genesys handoff), ADR-0019 (escalation contract),
ADR-0002 (Pipecat + Gradium), ADR-0009 (independent channel adapters), ADR-0040 (new)
**Classification:** Documentation + architecture (ADR)
**Status:** 🚧 In progress
**Priority:** Medium
**Branch:** `task/TASK-DOC-006-genesys-audio-connector-media-plane`

### Trigger

While confirming the target Genesys integration, the team read the Genesys
[AudioHook introduction](https://developer.genesys.cloud/devapps/audiohook/introduction),
[Protocol Reference](https://developer.genesys.cloud/devapps/audiohook/protocol-reference)
and [Audio Connector overview](https://help.genesys.cloud/articles/audio-connector-overview/).
This surfaced a naming/architecture ambiguity: **AudioHook is the protocol, and it
exposes two very different features** — a listen-only *Bot Transcription Connector*
(monitoring/transcription) and a **bidirectional *Audio Connector*** (the bot receives
**and sends** audio: `playback-started`/`playback-completed`, barge-in, `BotTurnResponse`).
Our V2V bot must **speak** to the caller, so only the **Audio Connector** feature fits.
ADR-0020 currently treats "Audio Connector or AudioHook routing" as interchangeable,
which is misleading.

### Objective

Record the correct target integration and remove the ambiguity, without any runtime
code change.

### Scope

- **ADR-0020** — replace the loose "Audio Connector or AudioHook" wording with the
  precise distinction (AudioHook = protocol; Audio Connector = the bidirectional
  feature required for V2V; Bot Transcription Connector = listen-only, not our path).
- **New ADR-0040** — "Genesys Audio Connector as the V2V media plane": document the
  three-plane split (media / control-routing / context-handoff), the Audio Connector
  constraints (premium app, max 5 integrations, one bidirectional stream per session,
  IVR channel, 15 min default call cap, PCMU/L16 codecs), and the overlap between
  Genesys-native barge-in/end-of-turn events and the runtime's bespoke detectors.
- **`docs/architecture/diagrams/target-v1-solution.drawio`** — label the telephony
  entry as Genesys Cloud CX via Audio Connector (AudioHook `wss`, bidirectional) and
  clarify that escalation routing is Genesys Architect + Platform API, with context
  carried on Architect variables / conversation attributes (not on the media socket).

### Out Of Scope

- Any code, port, adapter or endpoint change (no Genesys adapter is implemented yet;
  full Genesys voice routing stays deferred to Sprint 13, gated by OQ-006).
- Building or spiking the Audio Connector WebSocket server.
- Not runtime-affecting → no OpenTelemetry change.

### Acceptance Criteria

- ADR-0020 no longer implies AudioHook (bare) can route the bidirectional bot
  conversation; it points to ADR-0040 for the media-plane detail.
- ADR-0040 exists, is `Accepted` (target), lists the three planes, the Audio Connector
  constraints, and the barge-in/end-of-turn overlap, and is added to the ADR index.
- The target diagram shows Genesys + Audio Connector on the media edge and Genesys
  routing on escalation; `python3 -c "import xml.dom.minidom as m; m.parse(...)"` passes.
- `git diff --check` passes; all touched `docs/` content is in English (the target
  diagram stays French to match the existing artifact).

## TASK-DOC-002 - Reconcile Stale "Current-State" Documentation After Sprint 9

**Parent:** EPIC-001 (Product and architecture baseline)
**Related decision:** DEC-010 (measure before claiming), documentation-in-English rule
**Related review:** `docs/architecture/reviews/full-adversarial-review-2026-07-28.md`
(full adversarial code + documentation review; drift register D1–D14)
**Classification:** Documentation
**Status:** ✅ Done (2026-07-28) — validated and merged into `feat/restart-from-scratch`
(fast-forward `24995a9..4770ee0`, 15 files); ticket branch deleted (local + remote).
**Priority:** Medium
**Branch:** `task/TASK-DOC-002-doc-drift` (merged, deleted)

### Objective

Bring the top-level "current-state" documentation back in line with the code
delivered through Sprint 9. The full adversarial review found that nearly every
entry document still claimed the Java backend, React frontend and Docker Compose
were **removed** and that **only the STT-validation slice was built**, while on this
branch the backend runs (305 unit tests), the full streaming Voice2Voice loop and
RAG answer engine exist, and `docker-compose.yml` is present. This is a
correctness-of-record failure: it misleads every human and agent onboarding to the
project. TASK-DOC-001 did the equivalent refresh after Sprint 5; Sprints 6–9 drifted
the same docs again.

This task is **documentation-only** and not runtime-affecting (no OpenTelemetry
impact).

### Scope (drift register D1–D14)

- **D1** `README.md` — "removed" claim → two-service rebuilt stack + `docker-compose.yml` present; only React `frontend/` un-rebuilt.
- **D2** `docs/architecture/architecture.md` — branch note "not built yet: Java backend / RAG / streaming / WebRTC (Sprint 6)" → built through Sprint 9; flag legacy route/port tables further down.
- **D3** `docs/architecture/adrs/README.md` — "only the STT-validation slice is built" note → built vs target-only ADR split.
- **D10** `docs/architecture/adrs/README.md` — missing **ADR-0032** row (index jumped 0030 → 0033).
- **D4** `docs/README.md` — "only runnable code is voice-agent Sprints 1–5" → two-service stack.
- **D5/D11/D12/D13** `docs/engineering/development-guide.md` — "only Python slice runnable" banner; add a rebuilt-backend subsection (port **8080**, `/api/conversation/converse` family, split config classes); strengthen the legacy-`main` disclaimer so its `:8081`, `/ask*`, `/seed`, `agent/bot.py` names are not copied.
- **D6** `docs/operations/backlog.md` — "only STT-validation slice delivered" → two-service stack; V1 Core (BSS/PDF/comparison) still target.
- **D7** `docs/product/v1-scope.md` — "only STT validation built; no TTS" → full loop + RAG built; latency slices instrumented.
- **D8** `docs/architecture/channel-identity-boundary.md` — "only STT-in slice" → web channel↔backend split implemented; identity/BSS/Genesys still target.
- **D9** `CLAUDE.md` — "restart removes backend/frontend/voice-agent/Docker Compose" branch note + application-layout paragraph → rebuilt two-service stack.
- **D14** `product-backlog/backlog-index.md` — clarify that epic rows stay `Draft` by product policy while delivery has progressed through Sprint 9 (authoritative delivered state = sprint registry + story/task statuses).

### Out Of Scope

- Rewriting the ~400-line legacy `main` reference section in `development-guide.md`
  (kept as build reference, explicitly disclaimed).
- Any code change, endpoint change, or new diagram (Draw.io/Mermaid) edit.
- Product re-acceptance of epics (a separate Product/Architecture pass).
- The non-documentation findings of the review (endpoint auth, streaming STT-fail
  fallback, OTLP export, latency gate) — those need their own tickets.

### Acceptance Criteria

- No entry document (`README.md`, `CLAUDE.md`, `docs/README.md`,
  `architecture.md`, `adrs/README.md`, `development-guide.md`,
  `operations/backlog.md`, `v1-scope.md`, `channel-identity-boundary.md`) states
  that the backend/frontend/Docker Compose were removed or that only the STT slice
  is built, without immediately clarifying the Sprint 9 rebuilt state.
- The ADR index lists ADR-0032.
- The rebuilt backend contract (port 8080, `/api/conversation/converse` family) is
  documented and the legacy `:8081` / `/ask*` / `/seed` contract is clearly marked
  legacy-`main` reference.
- `git diff --check` passes; all touched docs remain in English.

### Follow-up Tickets Spawned By The Review (not part of this doc task)

- **TASK-BE-019** — authenticate/isolate `/api/knowledge/ingest`, `/sync`,
  `/api/conversation/answer`, `/retrieve` (`product-backlog/tasks/backend-hardening-tasks.md`).
- **TASK-WEB-018** — speak a degraded fallback on streaming STT failure, parity with
  the batch `/turn` 502 (`product-backlog/tasks/web-voice-tasks.md`).
- **TASK-OBS-001** — OTLP exporter / OpenTelemetry spans (backend Tracing→OTel bridge +
  voice OTLP), or record the accepted residual risk in ADR-0028
  (`product-backlog/tasks/observability-tasks.md`).
- **Latency (already tracked):** the ADR-0029 pilot-gate closure is covered by the
  existing **TASK-WEB-015** (perceived-latency optimization levers) + a warm live
  sample — no new ticket created.
