# QA Functional And Latency Report — TASK-WEB-028 (Browser WebSocket voice client)

## Executive Summary
- **Overall readiness:** GO for merge-ready. The interim browser `wss` client + its server
  wiring are built on the WEB-026 socle and WEB-027 factory (no bespoke socket/session code).
  Server-wiring and the interim language contract are covered by automated tests; the
  single-client capacity refusal (1013) is a socle guarantee surfaced by the client.
- **Main blockers:** none.
- **Residual risks:** (1) **No dynamic per-call language** on this transport — the effective
  language is the server default (fr-first), the client's declared language is captured for
  correlation only; deferred (candidate: listener-per-language or a pre-media signaling hook),
  tracked as an OQ and revisited at TASK-WEB-030. (2) Live end-to-end audio quality + latency
  through the HAProxy edge are validated at TASK-WEB-031 (needs a real socket + mic).

## Scope Tested
- **Epics / stories:** EPIC-006 / TASK-WEB-028 (ADR-0043 interim transport, ADR-0042 no-TURN,
  ADR-0033 WebRTC page stays, US-019 web voice journey).
- **Channels:** interim external browser WebSocket (`wss`) — one conversation at a time.
- **Providers / fakes:** manual fakes only (fake factory/session/loop/transport; the socle
  transport built for the single-client assertion is the real pipecat class, not bound).
  No DB / Ollama / network / live socket.
- **Environment:** local `voice-agent/.venv` (Python 3.14.2, pipecat 1.5.0).

## Functional Results
| Area | Status | Evidence | Notes |
|---|---|---|---|
| AC#1 — a session is built over the socle transport and run | PASS | `test_websocket_signaling.py::test_start_builds_transport_and_spawns_the_session_on_the_loop`; Behave `websocket_voice_client.feature` scenario 1 | Builds via `build_websocket_audio_transport` + shared `SessionFactory`, spawns `session.run()` on the shared loop |
| AC#1 — full duplex client (mic capture + playback) | PASS (static) | `static/ws.html` + `static/ws.js`: `getUserMedia`→`pcm-worklet.js`→PCM16/16k binary frames over `wss`; 16 kHz `AudioBuffer` playback; `open`/`barge_in`/`call_end` framing matches the server serializer | Live audio path is TASK-WEB-031 |
| AC#2 — capacity refusal surfaced, not silent | PASS | Single-client socle refuses a 2nd client with WS **1013** (`test_websocket_signaling` doc + Behave scenario 3 asserts the `SingleClientWebsocketServerTransport`); `ws.js` `onSocketClose` renders "Server busy — try again" on 1013 | No fabricated transcript on any failure branch |
| Interim language contract (declared captured, effective = server default) | PASS | `test_websocket_signaling::test_on_client_connected_records_the_declared_language_from_the_ws_query`; Behave scenario 2 (`declared "en"`, effective stays `fr`) | `?language=` on the WS URL + `open` frame captured for correlation; effective = `VOICE_WS_LANGUAGE` |
| Safe failure (mic denied, socket error/close) | PASS | `ws.js` sets an explicit error status on `getUserMedia` failure, `onerror`, and non-1000/1013 close codes; never invents a transcript | — |
| Config resolution (`VOICE_WS_PORT`/`VOICE_WS_LANGUAGE`) | PASS | `test_websocket_signaling::WebSocketConfigTest` (garbage/0 → default 8091; language normalised/lowercased; empty → None) | — |

## Latency Results
| Slice | p50 | p95 | p99 | Sample | Warm/Cold | Notes |
|---|---:|---:|---:|---:|---|---|
| Channel ingress → egress | — | — | — | 0 | — | **Not measurable in this ticket** (no live socket/mic in unit/Behave). The path reuses the shared session/ingress/egress probes (channel-egress probe in `pre_output`, STT/TTS spans, backend span) under one correlation id, so the canonical per-slice spans are emitted when run live. Rich per-slice p50/p95/p99 + active-session gauge = TASK-WEB-030; end-to-end mouth-to-ear through the edge = TASK-WEB-031. |

## Component Findings
| Brick | Status | Findings | Next action |
|---|---|---|---|
| `WebSocketSignalingService` (`web_voice/websocket_signaling.py`) | PASS | Thin adapter: socle transport + shared factory + shared loop; probes availability; records interim `voice.ws.*` events; best-effort teardown | Barge-in/end-of-turn seam = WEB-029; capacity gauge + per-slice spans = WEB-030 |
| Server wiring (`web_voice/server.py`) | PASS | `--websocket {auto,on,off}`, dedicated `VOICE_WS_PORT` (default 8091), shares the WebRTC loop or starts its own; clean shutdown order | — |
| Client (`static/ws.html` + `static/ws.js`) | PASS | PCM16/16k capture over `wss`, scheduled 16 kHz playback, 1013 busy surface, no fabricated output | Live validation WEB-031 |
| Shared telemetry dump (`web_voice/session_telemetry.py`) | PASS | Extracted from `webrtc_signaling`; identical evidence shape across WebRTC + WebSocket; WebRTC keeps `_log_telemetry` alias for backward-compat | — |

## Defects And Gaps
| Severity | Finding | Impact | Owner |
|---|---|---|---|
| Medium | No dynamic per-call language (effective = server default) | English speakers get fr-first answers in the interim; declared language is captured for correlation only | Deferred — OQ + WEB-030 (documented in ADR-0043 Client Outcome) |
| Low | `allowed_origins` left at pipecat default (env) | External edge must set the Origin allowlist (anti-CSWSH) | TASK-INFRA-010 / WEB-030 (socle seam already exposed) |
| Info | `start()` spawns `session.run()` fire-and-forget | A late transport bind failure surfaces in loop logs, not at `start()` | Acceptable interim; capacity/health hardening in WEB-030 |

## Open Questions
- Product: confirm fr-first-only is acceptable for the interim external demo (English deferred).
- Architecture: dynamic per-call language mechanism (listener-per-language vs pre-media
  signaling hook) — decide with WEB-030. ADR-0043 updated with the constraint + candidates.
- Technical: none.

## Recommendation
- **Go / No-go:** GO. Merge-ready pending the user's explicit merge request.
- **Required fixes before pilot:** set `allowed_origins` at the edge (INFRA-010); live
  functional + latency validation (WEB-031) before any external SLO claim.

## Live Client Validation (2026-08-24)
Run against a live server (`--provider gradium --backend stub --websocket on`, WS on 8091):
- **Plumbing (real socket, not fakes):** `ws://…:8091/?language=en` → sent `open` → received
  `{"type":"opened"}`; a **2nd concurrent** connection was closed with **WS 1013**
  (`"Server already has a connected client"`, AC#2); a binary PCM16 burst was ingested with the
  socket staying `OPEN` and no fabricated output. Same result on the `fixture` and `gradium`
  servers.
- **Browser mic turn:** `http://127.0.0.1:8090/ws.html` → Connect → mic → `Live` → spoken French
  turn → Gradium STT → stub answer → Gradium TTS played back; capacity refusal surfaced on a 2nd
  tab; Hang up released the session. **Validated by the user.**

## Test Evidence
- Unit: `tests/test_websocket_signaling.py` (8) green. Full suite **538** green (530 baseline + 8 new).
- Behave: `features/websocket_voice_client.feature` (3 scenarios / 12 steps) green; full suite
  **15 features / 42 scenarios / 192 steps** green (was 14/39/180).
- Adversarial code review: **93/100 — Pass** (no blocking findings; 1 Medium + 1 Low + 1 Info,
  all deferred/accepted with owners).
