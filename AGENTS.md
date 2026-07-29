# Guidance for AI agents — Voice Support Bot

## Repo & git

- `voice-support-bot` is a **separate git repository** (default branch `main`) nested in the `BMad` workspace (which is another repository). Commit/push bot work **in this repository**, not in `BMad`.
- **Ledgers and docs live in THIS repo.** When working on the Voice Support Bot, the `done-tasks.md` you append to is **`voice-support-bot/done-tasks.md`** — never the workspace-root `BMad/done-tasks.md` (that one logs only the `cursor-usage-dashboard` project). The same applies to `product-backlog/`, `docs/`, and any planning file: always use the copies **inside `voice-support-bot/`**. If you catch yourself editing a file above this directory for bot work, stop and move it here.
- **This repo is self-contained for guidance.** When working here, use only this repository's `CLAUDE.md` / `AGENTS.md` and the skills under `voice-support-bot/.cursor/skills/`. Do **not** apply the workspace-root `BMad/claude.md`, `BMad/agents.md`, or root `.cursor/skills/` — those govern `cursor-usage-dashboard/`, not this project.
- **Two-level branch model (decision 2026-07-29): sprint branch + ticket branches.**
  Each sprint has one integration branch `feat/sprint-NN-short-theme` (e.g.
  `feat/sprint-10-pilot-latency`) created from `feat/restart-from-scratch` at sprint start.
  Every development ticket still gets its own branch — `us/US-XXX-short-name` (stories),
  `fix/BUG-XXX-short-name` (bugs), `task/TASK-XXX-short-name` (tasks) — but created **off the
  current sprint branch**, not off `feat/restart-from-scratch`. Do not commit directly on
  `main` or on `feat/restart-from-scratch`.
- **Ticket branch → sprint branch.** When a ticket is merge-ready (dev tests + adversarial
  review ≥ 90% + QA GO) and the user asks to merge it, merge the ticket branch **into its
  sprint branch** with `git merge --no-ff` (keep an explicit integration marker). The sprint
  branch is what accumulates the sprint's work.
- The user is the final validator. Do not merge any branch — ticket **or** sprint — unless the
  user explicitly asks for the merge.
- When the user validates a ticket, record the validation, rerun checks, commit
  and push the ticket branch automatically. Merge (ticket→sprint) still needs an explicit
  user request.
- **Closing a sprint = merge the sprint branch into `feat/restart-from-scratch` + update status.**
  When the user says a sprint is closed, first merge `feat/sprint-NN-…` into
  `feat/restart-from-scratch` (only on the user's explicit request), then — the merge is only
  step one — you MUST also update the sprint status in the same session (a fast-forward merge
  carries no closure commit, so nothing updates itself): (1) the sprint file `## Status` +
  roadmap row → `✅ Done (closed <date>)`, (2) the `backlog-index.md` sprint registry row →
  `✅ Done (<date>)`, (3) a dated entry in **this repo's** `voice-support-bot/done-tasks.md`
  summarizing the sprint. Then commit + push these doc updates.
- **Commit after each task**; do not leave code uncommitted.
- On `feat/restart-from-scratch`, the previous implementation directories
  (`backend/`, `frontend/`, `voice-agent/`) and `docker-compose.yml` are
  intentionally removed. `main` is the backup/reference for the old code.

## Before you edit

1. On the restart branch, create new implementation scaffolds only when the
   corresponding backlog story is selected.
2. No development starts without a ticket. If the user asks for a change without
   an existing ticket, create the ticket first, ensure the sprint branch
   `feat/sprint-NN-short-theme` exists (create it from `feat/restart-from-scratch`
   at sprint start), then create or switch to the dedicated ticket branch **off the
   sprint branch**.
3. Java backend: follow the `java-backend-developer` skill + `code-guidelines`
   (methods <= 20 lines, classes <= 200 lines, no Javadoc on ports).
4. Pure domain (no Spring annotations); wire services through `@Bean` in
   infrastructure configuration.
5. Tests: manual fakes, GIVEN/WHEN/THEN, **no Mockito**.
6. Voice runtime: preserve the target architecture direction (Pipecat + provider
   adapters), but rebuild the runtime from scratch on this branch.
7. Documentation files under `docs/` must be written in English.
8. Documentation work : use `.cursor/skills/technical-writer/SKILL.md` before creating, editing, translating or reviewing technical docs.
9. Skill work : use `.cursor/skills/skill-creator/SKILL.md` before creating,
   modifying, evaluating or packaging local agent skills.
10. QA / test strategy work : use `.cursor/skills/qa-functional-latency/SKILL.md`
   before writing Gherkin scenarios, Java Cucumber tests, Python Behave tests,
   pilot readiness reports, UI validation plans or latency reports by brick.
11. Adversarial code review : use `.cursor/skills/adversarial-code-review/SKILL.md`
   before QA acceptance of a user story. The implementation must reach at least
   90% satisfaction unless Product or Architecture explicitly accepts the
   residual risk.
12. OpenTelemetry is mandatory for runtime work: every development touching
   runtime behavior must add or update traces, metrics and structured logs needed
   for monitoring, latency analysis and troubleshooting, or explicitly mark the
   story as not runtime-affecting.
13. Diagram work : use `.cursor/skills/diagram-drawer/SKILL.md` before creating, editing or reviewing Mermaid/Draw.io diagrams.
14. Presentation work : use `.cursor/skills/presentation-maker/SKILL.md` to create high-level technical/strategy decks from `~/Downloads/Presentation.odp`.
15. Architecture decisions : use `.cursor/skills/software-architect/SKILL.md` and create or update an ADR under `docs/architecture/adrs/`.

## User Story Delivery Workflow

- Follow `docs/operations/development-workflow.md` for every V1 user story.
- Create or confirm the ticket before implementation; no ticket means no
  development.
- Work on a dedicated ticket branch named after the ticket, created off the current
  sprint branch `feat/sprint-NN-short-theme`; merge it back into the sprint branch
  (`git merge --no-ff`) when merge-ready and the user asks.
- Assign implementation to the relevant frontend and/or backend developer skill.
- Start QA in parallel with development; QA writes Gherkin intent, fixtures,
  Cucumber/Behave tests and latency expectations while development happens.
- Run `adversarial-code-review` before QA acceptance. The developer must fix
  findings until the adversarial reviewer is at least 90% satisfied, unless
  Product or Architecture explicitly accepts the residual risk.
- After adversarial review passes, QA runs functional and latency validation.
  Any QA bug must become an explicit bug ticket using
  `product-backlog/templates/bug-ticket-template.md`, then restarts the loop:
  developer fix -> adversarial review -> QA retest.
- A story is not done until implementation, developer tests, adversarial review,
  OpenTelemetry coverage, QA tests and required latency reporting are complete.
- Passing all gates makes a branch merge-ready only. Merge only when the user
  explicitly asks.

## Common mistakes to avoid

- Confusing **LLM** and **embedding**: they are 2 distinct models. Chat uses Mistral (API), embedding uses Ollama (`nomic-embed-text`, 768 dim). "Switching to Mistral" does NOT change embeddings (Mistral embedding auto-config is excluded).
- Running `ALTER TABLE vector_store` to add metadata: unnecessary, metadata is stored as **JSONB**. However, **changing the embedding model** (and therefore the dimension) requires recreating the table + re-syncing.
- Forgetting that rows seeded through the old `curl /ingest` have no `source_id` -> `deleteBySource` does not clean them up. Empty `vector_store` once before the first sync.
- Adding a method to an outbound port (`VectorStorePort`, etc.) without updating **all** implementers, including **test fakes**.
- Returning a `mistral-embed` vector type (1024) without aligning `pgvector.dimensions` — silent mismatch on insert/search.
- Adding a dependency to parse YAML front-matter: SnakeYAML is already present (Spring Boot transitive dependency).
- Putting Spring annotations in the domain, or injecting a connector while forgetting the `@Bean` (it will not be in `List<KnowledgeSourceConnector>`).
- Believing `mvn test` needs a DB/Ollama: there is no `@SpringBootTest`; tests are domain units with fakes.
- Putting bot learnings in the root `BMad` `CLAUDE.md`: it belongs to another project (`cursor-usage-dashboard`). Bot knowledge files live in `voice-support-bot/`.
- Starting Billing V1 from scratch: keep the POC voice/RAG/orchestrator foundation, but rebuild the business core around the BSS and invoice comparison.
- Using a generic MCP as the main BSS access path in customer runtime: prefer a typed read-only business port (`BssBillingPort`) with BSS adapters; reserve MCP for exploration and internal tools.
- Coupling the product core to a specific LLM/STT/TTS SDK: expose these capabilities through configurable ports/adapters so providers can be benchmarked and swapped easily.
- Presenting `bridge_server.py` as the V1 voice target: false. The V1 target starts on Gradium + Pipecat (`agent/bot.py`); the custom bridge remains a historical POC / fallback.
- Writing new `docs/` content in French: documentation must be in English, even when the working conversation is in French.
- Closing the product around billing only: V1 = invoice explanation, but the architecture must remain extensible to other operator support domains.
- Creating a separate repository for the product backlog when the user mainly wants to keep it with the project: by default, store artifacts in `product-backlog/` in the `voice-support-bot` repo unless an external git repository is explicitly requested.
- Writing product EPICs/user stories without the `product-business` skill: this skill keeps stories at the level of need, value, business rules, and observable acceptance, without API or implementation details.
- Taking `billing-service` as the Galaxion source for invoices: it is no longer used. For V1, target only `billing-api`.
- Looking for a structured Galaxion invoice-line endpoint without proof: none has been identified. Retrieve the PDF through `bill-run-documents` and use a deterministic `InvoicePdfExtractor`.
- Letting the LLM read the invoice PDF directly to calculate amounts: forbidden. First extract structured JSON, verify reconciliation, then formulate the explanation.
- Placing Mermaid `retrieval` / `generation` labels on ambiguous internal handoffs: labels must live on the edge representing the real interaction, typically adapter -> PgVector or adapter -> external LLM.
- Creating/editing Draw.io XML with important unanchored connections: use explicit `exitX/exitY` and `entryX/entryY` anchors, especially with swimlanes and labeled edges.
- Authoring draw.io diagrams with edges that have no fixed anchor points — floating connections drift and render "detached" from boxes, especially when nodes are nested in swimlanes (relative coords). Always set explicit `exitX/exitY/exitDx/exitDy` + `entryX/entryY/entryDx/entryDy` (fractions 0→1 of the box border) on every `<mxCell edge="1">` so arrows stay glued to a precise border point and labels land on the segment.
- Forgetting that draw.io swimlane children use coordinates **relative to the swimlane top-left including the `startSize` title bar** — when nesting nodes into a swimlane, subtract the swimlane origin and add the header offset, or boxes land in the wrong place. Validate every `.drawio` edit for well-formed XML (`python3 -c "import xml.dom.minidom as m; m.parse('file.drawio')"`).
- Generating a presentation by patching `Presentation.odp` without visual validation: the XML can contain text while still opening blank. If LibreOffice/soffice is unavailable, generate a `.pptx` with standard text shapes.
- Overfilling presentation template frames: use a large layout, one idea per slide, and two short bullets maximum to keep presentations readable.
- Presenting the omnichannel vision as industrialized because the diagram is clean: false. Until channel/backend contracts, an escalation contract, SLOs, observability, per-channel rate limiting, and degraded modes are defined/tested, this is a solid MVP with a healthy vision, not a production platform.
- Adding WhatsApp, Genesys, or a new channel before formalizing the shared contract (`channel`, `external_session_id`, `message_id`, `idempotency_key`, `reply_mode`, `escalation_context`) — that duplicates logic and couples channels.
- Making an architecture decision without an ADR: every structural decision must be documented under `docs/architecture/adrs/` with context, decision, consequences, and alternatives.
- Letting Genesys own RAG, billing reasoning, guardrails, escalation policy, or
  conversation memory: wrong boundary. Genesys owns contact-center operations;
  the backend owns conversation intelligence and handoff content.
- Claiming a voice SLO from a single end-to-end timing: first decompose latency
  into channel ingress, end-of-turn, STT, backend, BSS/PDF, comparison, RAG, LLM,
  TTS, channel egress and Genesys handoff.
- Adding Genesys voice routing without testing barge-in and interruption across
  the media layer and voice runtime: cancellation behavior is a cross-component
  integration concern, not a backend-only feature.
- Treating missing implementation directories on `feat/restart-from-scratch` as
  an accident: they were removed intentionally so the project can restart from
  the backlog and architecture baseline.
- Writing QA tests without checking product intent first: use
  `qa-functional-latency`, and escalate functional ambiguity to
  `product-business` instead of inventing expected behavior.
- Shipping runtime behavior without OpenTelemetry traces, metrics and structured
  logs: every runtime story must expose the correlation id, latency slice timing,
  outcome status and sanitized error context needed for monitoring and QA.
- Starting development without a ticket: if the user asks for an unticketed
  change, create the user story, bug or task ticket first.
- Merging because tests or QA passed: the user is the final validator; no branch —
  ticket→sprint or sprint→`feat/restart-from-scratch` — is merged unless the user
  explicitly requests it.
- Branching a ticket off `feat/restart-from-scratch` instead of the current sprint branch
  `feat/sprint-NN-short-theme` — ticket branches must fork from (and merge back into) the
  sprint branch (decision 2026-07-29). Only the *sprint* branch forks from / merges into
  `feat/restart-from-scratch`.
- Treating "close the sprint" as merge-only and leaving the sprint status stale — closing a
  sprint means (1) merge the sprint branch into `feat/restart-from-scratch` (on explicit user
  request) and (2) update status: a fast-forward merge carries no closure commit, so the sprint
  file, `backlog-index.md` registry and `done-tasks.md` stay "In progress/Planned" unless you
  update them in the same session. On sprint closure: merge, then flip all three to `✅ Done`,
  then commit + push the doc updates.
- Patching repeated Markdown fields like `**Status:**` without the ticket header
  in context: it can update the wrong story. Reread the target block before
  committing.
- Reviewing only tracked diffs: `git diff --stat` does not show untracked
  scaffolds. Always inspect `git status --short` before staging or committing.
- Treating local telemetry events as enough for runtime work: STT/runtime
  scaffolds must expose events, metrics and structured logs with correlation id,
  provider, outcome and duration.
- Including the current user turn in LLM conversation history when building context — if `addUserTurn(question)` is called before `buildHistory()`, the history already contains the question being asked. This duplicates the question (once in history, once in the user message) and breaks "empty history" detection for first-message greeting logic. Exclude the last turn from `buildHistory()` output.
- Using `String.contains()` for keyword matching in intent classification — short keywords like `"ip"` match inside unrelated words like `"équipement"`, `"équipe"`. Use word-boundary matching (check that adjacent characters are not alphanumeric) instead.
- Sending `conversationId` (camelCase) from a Python bridge to a Spring Boot backend that expects `conversation_id` (snake_case via `@JsonProperty`) — Spring silently ignores the unrecognized field and uses the default value. Always verify the Jackson field name in the Java DTO.
- Forgetting to stop the `AudioBufferSourceNode` when clearing an audio queue — emptying the queue array and resetting flags does not stop audio already playing. Call `source.stop()` on the current source node.
- Leaving dead adapter code in the backend after a pipeline migration (e.g. Deepgram STT → Gradium) — unused ports, adapters, and config accumulate confusion and false dependency impressions. Audit and remove legacy pipeline code when the replacement is confirmed working.
- Filtering vector search results by `domain` metadata without ensuring all chunks have the metadata set — legacy chunks stored without `domain` are silently excluded. Always store a default `domain` value (e.g. `"general"`) and expand the search filter to include it.
- Feeding a WAV container to Gradium STT — it expects **raw PCM16 mono 16 kHz** (`input_format=pcm_16000`, `Content-Type: audio/pcm`). A WAV 44-byte header is read as leading samples (click). Generate fixtures as raw `.pcm` (macOS `say` → `wave.readframes()` to strip the header); don't name raw PCM `.wav`.
- Committing STT audio fixtures as `.txt`/ASCII placeholders — they pass the deterministic `FixtureSttProvider` (which reads the `.txt` sidecar) but no real engine can transcribe them, so a live provider run is silently blocked. Commit real audio, and keep the `.txt` sidecar (resolved via `audio_path.with_suffix(".txt")`).
- Scoring STT quality with a raw whitespace WER against a real engine — punctuation, case and accents (`telephone` vs `téléphone`, `Bonjour` vs `Bonjour.`) inflate WER to the point of failing correct transcripts. Normalize reference and hypothesis (lowercase, strip punctuation, fold accents) before WER; keep the raw transcript for audit.
- Assuming batch STT latency is a fixed cost — it scales with audio duration (Gradium processes the whole clip after upload). Use streaming/partial transcription as the latency lever, and always report the utterance length alongside the latency.
- Omitting an un-instrumented pipeline slice from a latency report — always emit every canonical slice and mark missing ones `"measured": false` with a reason/owning ticket, so a gap is never mistaken for a fast slice. When one slice can be fed by several span names, let the first present name win so distributions from different paths don't mix.
- Running git commands for bot work from the `BMad` workspace root — `voice-support-bot` is a **separate nested git repository**. `git checkout <vsb-branch>` / `git stash` executed from the root repo fail with "pathspec did not match" or land the stash in the wrong repo. Always `cd voice-support-bot` (confirm with `git rev-parse --show-toplevel`) before staging, committing, stashing or switching branches for bot work.
- Editing knowledge/doc files without first confirming the working tree matches HEAD — a stale or reverted working copy can silently drop already-committed content, so an append re-commits a regression. Run `git status` / `git diff HEAD` and restore from HEAD before appending.
- Validating a WebRTC voice turn with a **pure-silence** trailing pad — Opus DTX sends no packets during digital silence, so an energy-based end-of-turn aggregator never flushes and the US-036 telemetry stays empty (while `received_bot_audio` is `True` from the output track's silence keepalive, which is misleading). Pad file-based test clips with low-amplitude noise (peak ≪ ~1000), never zeros; a real mic works because of its ambient noise floor. Hold a headless client's call open a fixed window instead of hanging up on the first bot frame. TASK-WEB-007.
- Assuming Pipecat's `SmallWebRTCTransport` is audio-only-light or that its signaling is framework-free — it hard-imports `cv2` (`av`+`opencv-python`, duplicate `libavdevice` dylib → benign macOS `objc` warning), and `SmallWebRTCRequestHandler` imports FastAPI. Keep the transport behind the import guard and do signaling directly on `SmallWebRTCConnection` (no FastAPI). The threaded stdlib server needs one persistent asyncio loop (`web_voice/async_loop.py`) for the streaming session; submit coroutines with `run_coroutine_threadsafe`. See ADR-0022.
- Running a WebRTC/streaming server in the background with a trailing `&` inside a one-shot tool shell — the process is reaped when the shell returns (`Connection refused` on the next call). Launch long-running servers as a proper background job.
- Sharing one working directory between two agents on different tickets — a parallel session switching branches corrupts the other's edits (files land on the wrong checkout). Use a dedicated `git worktree` per concurrent ticket, then `git worktree remove` when done.
- Assuming Silero VAD auto-wires into a Pipecat pipeline (`TransportParams(vad_analyzer=...)`) — in pipecat 1.5.0 there is no `vad_analyzer` field and no `VADAnalyzer` consumer in the transports. `SileroVADAnalyzer` is a standalone `analyze_audio(pcm) -> VADState` component you drive by hand — same effort as the existing energy detector. Keep the detector for onset; treat Silero as a drop-in verdict upgrade only (ADR-0025).
- Building a bespoke barge-in flush/cancel instead of Pipecat's native path — `broadcast_interruption()` sends an `InterruptionFrame` that cancels each processor's in-flight task and flushes the output transport's audio buffer. Gate the trigger on bot-speaking state (tracked from the `BotStarted/StoppedSpeakingFrame` the output transport emits **upstream**); firing on every onset disrupts normal turns.
- Wrapping an interruptible async loop in `except Exception` only — `asyncio.CancelledError` is a `BaseException` and won't be caught, so cleanup (WebSocket `aclose()`) is skipped on barge-in. Add `except asyncio.CancelledError` (report + re-raise) and a `finally` best-effort close.
- Emitting the `voice.tts.first_audio` span for a non-success turn (interrupted/failure) with total-elapsed — `pipeline_timing` groups by span name with no outcome filter, so it pollutes the `tts_first_audio` p95. Emit the span with the real time-to-first-audio and only when audio actually played; keep elapsed on the outcome event.
- Relying on browser `echoCancellation` alone for barge-in — without headphones the bot's speaker→mic echo still leaks through and an energy VAD self-interrupts the bot. The echo is continuous (N-frame confirmation can't reject it); the real discriminator is amplitude. Gate the barge-in cut on a raised amplitude threshold + N-frame sustained-onset confirmation, keep opening the STT session on normal onset, and make both env-tunable (echo levels are per-setup) — validated live for TASK-WEB-008 (ADR-0025 point 7).
- Ending the call on the *first* detected closing word — abrupt and false-positive-prone. Use a confirmation turn (US-041, ADR-0035): suppress the answer, ask "Souhaitez-vous autre chose ?", and end only on a done-confirmation OR a bounded confirmation-scoped silence timeout. Keep closing detection deterministic/no-LLM (accent-insensitive word-boundary matching with negation + embedded-request guards); make phrase sets/timeouts env-tunable (`VOICE_FAREWELL_*`).
- In the end-of-call confirmation turn, checking only `is_done_confirmation(text)` and ignoring a repeated goodbye — a customer re-saying "au revoir"/"non, au revoir" then falls into the "answer normally" branch and the call never ends. A repeated `detect_closing` match during confirmation must also count as done.
- Writing a bespoke end-of-call close path instead of reusing the existing drain — delegate ending to an injected `end_call(signal)` callback (keeps the FrameProcessor transport-agnostic + unit-testable) and wire it in the signaling to the TASK-WEB-008 `drain()` path; record a `voice.call_end` reason (`customer_farewell` vs `client_stop`/`client_drop`).
- Guessing pipecat test-helper import paths — `SleepFrame` and `run_test` are in **`pipecat.tests.utils`**, not `pipecat.frames.frames`. Needed to drive time-based FrameProcessor tests (e.g. a confirmation silence timeout).
- Faking a telemetry recorder with `SimpleNamespace` — processors call `telemetry.record(name, correlation_id=..., **attrs)`, which a `SimpleNamespace` lacks. Use the real `voice_common.telemetry.TelemetryRecorder` in tests (also lets you assert emitted events).
- Building a partial turn envelope (only `correlation_id`) in voice tests/Behave — the answer stage builds the backend request from it and fails without `conversation_id`, `channel`, `language`. Populate the full envelope.

## Checklist After Substantive Changes

- [ ] If implementation scaffolds exist, run their relevant tests.
- [ ] On documentation-only changes, run `git diff --check`.
- [ ] If a REST contract changed: update `docs/` (architecture.md, README, API).
- [ ] If there is a new bean/port: wire it in `DomainServiceConfig`.
- [ ] If runtime behavior changed: add/update OpenTelemetry traces, metrics and
      structured logs, or document why the story is not runtime-affecting.
- [ ] Update `docs/` together with code (not as a separate batch).
