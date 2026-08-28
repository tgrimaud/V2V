# BUG-018 — A voice turn can stay "thinking" until the user manually refreshes

## Header

- **Bug ID:** BUG-018
- **Title:** The web voice UI can stay stuck in "thinking" for a long time and only recovers on a manual page refresh
- **Status:** New (planning only — investigation done, fixes ticketed, not yet implemented)
- **Severity:** High
- **Priority:** P1
- **Detected by:** User validation (pilot)
- **Detected date:** 2026-08-27
- **Related user story:** US-019 (ask from a web voice chat)
- **Related epic:** EPIC-006 (Voice2Voice journey foundation) / EPIC-010 (observability, latency & pilot validation) / EPIC-012 (pilot deployment & operations)
- **Branch:** `chore/port-bug-017-backlog` (backlog port onto `feat/restart-from-scratch`; fixes land on the P1 ticket branches below)
- **Owner:** Cross-functional (Voice runtime developer + Frontend/`web_voice` + Ops)
- **ID note:** Originally filed as **BUG-017** on the retired `fix/BUG-017-voice-turn-hang` branch; renumbered to **BUG-018** to avoid collision with the mainline **BUG-017** (barge-in count anomaly on headless WS turns). The three P1 fixes were originally **TASK-WEB-037 / TASK-WEB-038 / TASK-OPS-010**; the two WEB tickets were renumbered to **TASK-WEB-045 / TASK-WEB-046** to avoid collision with the v0.7.0 aiohttp single-port tickets of the same number, while **TASK-OPS-010** was free on the mainline and kept.

## Problem Statement

A pilot user reported that, after asking a question, the web voice UI stayed in the
"thinking" state for a long time and never produced a spoken answer or an error; the
only way to recover was to **refresh the page**. The turn reached a dead-end with no
terminal outcome surfaced to the user.

## Environment

- **Environment:** pilot (eir-ai4cc-tst)
- **Channel:** web voice (browser → voice bridge → conversation backend)
- **Provider configuration:** Gradium streaming STT/TTS, Mistral RAG backend (co-located), streaming answer path on (`VOICE_BACKEND_STREAM=1`, ADR-0037)
- **Topology:** two voice bridges behind voice VIP (HAProxy TLS edge, `timeout tunnel 1h`); two backends behind the backend VIP; browser ↔ bridge over a long-lived WebSocket/WebRTC connection
- **Build or commit:** pilot build at report time (retained logs go back ~22 h, to the 2026-08-26 deploy)
- **Correlation ID:** not captured by the user at report time (see the observability-retention limit below)

## Reproduction Steps

Not reliably reproducible on demand. The user-observed sequence was:

1. Given an active web voice session with the bot.
2. When the user asked a question (a normal turn).
3. Then the UI entered "thinking" and stayed there indefinitely; no spoken answer,
   no error, no retry affordance — recovered only by manually refreshing the page.

## Expected Result

Every voice turn reaches a **terminal, user-visible outcome within a bounded time**:
the caller hears an answer, hears a safe spoken fallback, or the UI leaves the
"thinking" state and offers a retry. A turn must never strand the UI with no terminal
signal and force a manual refresh.

## Actual Result

The UI remained in "thinking" with no answer, no error and no timeout, until the user
refreshed the page.

## Evidence

Read-only investigation across both voice bridges and both backends
(no configuration or code changed):

- **Not reproduced in the retained logs.** In the ~22 h of retained history (json-file
  rotation, `RestartCount=0`, back to the 2026-08-26 deploy) **every turn was served**:
  the BE-025 streaming inter-signal timeout (`outcome=timeout`) fired **0×**, and there
  were **0 real-user** `ERR_UPSTREAM`. An earlier occurrence (if any) predates the
  retention window and is unrecoverable — see the observability-retention limit below.
- **Self-recovering stalls that DID occur (not the reported dead-end):**
  1. A Gradium streaming-STT finalize timeout (~10 s) that degraded to a spoken reply
     (the turn still terminated) — already being addressed by TASK-STT-014.
  2. Transient Mistral upstream slowness that produced `ERR_UPSTREAM`, but **only on the
     synthetic `verify-mobile` smoke probe**, not on a real user turn.
- **Leading hypothesis (architectural, evidence-consistent, not observed firing):** the
  streamed voice turn has **no overall wall-clock deadline** — only a per-read socket
  timeout on the backend HTTP hop. A backend that trickles bytes but never sends a
  terminal `done`/`error` (or a mid-turn connection break with no terminal signal) can
  hold the turn open with the UI in "thinking" and no terminal control signal, which
  matches the reported symptom. Compounded by a long-lived browser↔bridge connection
  (HAProxy `timeout tunnel 1h`) and no bridge active-session drain, so a
  deploy/failover/WS break mid-turn can strand the UI.

## Impact

- **Customer impact:** a dead-end turn — the caller waits, gets nothing, and must know
  to refresh to recover. Erodes trust in the voice assistant and can end the session.
- **Operational impact:** hard to triage because the failure did not leave a terminal
  outcome or (in the reported case) a captured correlation id; the short log-retention
  window makes an after-the-fact root cause unrecoverable.
- **Pilot-readiness impact:** a "must never strand the user" reliability gap on the
  primary Voice2Voice journey (US-019); a blocker for a confident pilot sign-off even
  though it was not reproduced in the retained window.

## Leading Hypothesis And Fix Tickets

The reported symptom is best explained by an **architectural hang-until-refresh risk**
(no observed firing in the retained logs, but the code path allows it). Three P1 fixes
harden the journey so a turn can no longer strand the UI, and a terminal outcome is
always surfaced:

- **TASK-WEB-045 (P1)** — an overall wall-clock deadline for a streamed voice turn, in
  addition to the per-read socket timeout, degrading to the spoken fallback when
  exceeded (bounds the "trickles bytes but never terminates" case).
- **TASK-WEB-046 (P1)** — a guaranteed terminal UI control signal on every turn outcome
  plus a browser-side watchdog, so a dropped/broken connection or a backend
  error/timeout can no longer leave the UI in "thinking".
- **TASK-OPS-010 (P1)** — a bridge active-session `/drain` endpoint wired into the
  Ansible voice deploy, so a bridge recreate/deploy/failover drains live calls instead
  of hard-cutting them mid-turn (closes the documented gap in
  `deploy/ansible/group_vars/voice.yml`).

Contributing mitigation already in flight (not duplicated here): **TASK-STT-014** (reduce
the Gradium post-end-of-turn STT finalize tail) addresses the self-recovering STT stall
noted above.

Architecture references: ADR-0037 (first-sentence backend streaming to TTS — the
`StreamedAnswerRunner`/SSE path that lacks an overall deadline), ADR-0029 (pilot latency
criterion / mouth-to-ear budget the deadline must respect), ADR-0025 (native barge-in /
interruption + audio drain the terminal-signal and drain work build on).

## Secondary / Follow-up Defects (NOT P1 — noted, do not expand into P1 tickets)

- **P2 — SSE client-abort mislogged as an internal error.** When the browser aborts an
  in-flight SSE turn (normal on refresh/navigation/barge-in), the backend logs it as an
  internal error with an absent correlation id (`ERR_INTERNAL correlation_id=n/a`, from a
  broken-pipe / client-abort / async-not-usable condition), and the generic unexpected-error
  handler then fails again trying to write to an already-committed async response. A benign
  client disconnect should be logged as a client abort (debug/info), not an internal error,
  and must not trigger a second failing write. Track as a separate P2 hardening ticket.
- **P3 — worst-case blocking-LLM turn cost.** Even outside the streamed path, a blocking
  backend turn is bounded only by coarse timeouts; a slow-but-not-dead upstream can produce
  a long perceived wait. TASK-WEB-045's deadline covers the streamed path; a symmetric
  bound on any remaining blocking path is a P3 follow-up.
- **P3 — observability retention / correlation capture.** Retained voice/backend logs cover
  only ~22 h (json-file rotation), and the reported incident carried no captured correlation
  id, so an earlier occurrence is unrecoverable. Longer/centralized retention (building on
  TASK-OPS-007) and surfacing the correlation id in the UI would make this class of incident
  diagnosable. P3 follow-up (observability), gated behind the TASK-OPS-007 pipeline.

## Acceptance Criteria For Fix

This bug is considered addressed when the three P1 tickets are delivered and validated:

- [ ] A backend that streams with sub-deadline inter-byte gaps but never terminates still
      ends the turn within the wall-clock deadline, degrading to a spoken fallback
      (TASK-WEB-045).
- [ ] Killing/breaking the browser↔bridge connection mid-turn makes the UI leave
      "thinking" within a bounded wait and offer a retry (TASK-WEB-046).
- [ ] A bridge redeploy during an active call drains rather than hard-cuts the call
      (TASK-OPS-010).
- [ ] OpenTelemetry emits the deadline-hit / terminal-signal / drain outcomes so the
      class of incident is observable next time.
- [ ] Each P1 ticket passes adversarial review ≥ 90% + QA before merge.

## Developer Notes

Filled per P1 ticket during resolution. Investigation-time notes (read-only):

- Overall-deadline gap lives on the streamed path: `voice-agent/conversation_backend/http_backend.py`
  applies the socket timeout **per read** via `urllib.request.urlopen(..., timeout=...)`, and
  `voice-agent/voice_pipeline/streaming_answer.py` (`StreamedAnswerRunner`) consumes one SSE
  event at a time — neither imposes an end-to-end turn budget.
- Terminal-signal vocabulary already exists (`web_voice/control_signals.py`,
  `web_voice/websocket_framing.py`: `playback_completed` / `n`), but it is not guaranteed on
  every failure/teardown outcome, and the browser client has no watchdog for a missing signal.
- The bridge audio `drain()` (TASK-WEB-008 / ADR-0025, in `web_voice/streaming_runtime.py` +
  `web_voice/webrtc_signaling.py`) drains the current turn's TTS buffer; it is **not** an
  active-session HTTP `/drain` for graceful deploy — that is the documented gap in
  `group_vars/voice.yml` and the subject of TASK-OPS-010.

## QA Retest

- **Retested by:** (per P1 ticket)
- **Retest date:**
- **Scenarios rerun:** deadline-exceeded turn; mid-turn connection kill; redeploy during an active call
- **Result:** pending

## Closure

- **Closed by:**
- **Closed date:**
- **Closure reason:** pending (closes when TASK-WEB-045 + TASK-WEB-046 + TASK-OPS-010 are validated)
