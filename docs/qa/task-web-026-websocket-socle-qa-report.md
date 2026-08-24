# QA Functional And Latency Report — TASK-WEB-026 (WebSocket audio socle + framing)

## Executive Summary
- **Overall readiness:** GO for merge-ready (socle + framing scope). Both acceptance
  criteria covered by automated tests; full voice-agent regression green.
- **Main blockers:** none.
- **Residual risks:** end-to-end live `wss` acceptance (a real browser connecting through
  the edge) is proven only at TASK-WEB-028 (client) + TASK-INFRA-010 (HAProxy `wss`); this
  ticket proves the socle + framing at component level, by design (ADR-0043 scope).

## Scope Tested
- **Epics / stories:** EPIC-006 / TASK-WEB-026 (ADR-0043, ADR-0042, ADR-0040).
- **Channels:** interim external browser WebSocket audio path (no TURN).
- **Providers / fakes:** none required — component test of the framing serializer and the
  transport socle builder against the real pipecat `SingleClientWebsocketServerTransport`.
- **Environment:** local `voice-agent/.venv` (Python 3.14.2, pipecat 1.5.0, websockets 13–16).

## Functional Results
| Area | Status | Evidence | Notes |
|---|---|---|---|
| AC#1 — wss socle without FastAPI, shared-loop-driven | PASS | `features/websocket_transport.feature` sc.1; `test_websocket_support.py` (websockets variant, no-FastAPI build) | Socle is `pipecat.transports.websocket.server` (websockets-based); FastAPI never imported |
| AC#2 — deterministic JSON-control vs binary-audio demux | PASS | `features/websocket_transport.feature` sc.2; `test_websocket_framing.py` (17 tests) | binary→`InputAudioRawFrame` PCM16/16 kHz; text→JSON control; never crossed |
| AudioHook-shaped control vocabulary (Genesys reuse) | PASS | `features/websocket_transport.feature` sc.3 (barge_in→interruption); framing tests (open/opened, close/closed, language, ping/pong, call_end) | Shape adopted, not exact schema (YAGNI, ADR-0043) |
| Anti-CSWSH Origin allowlist seam | PASS | `test_websocket_support.py::test_origin_allowlist_seam_is_honoured_when_provided` | Effective allowlist set at INFRA-010/WEB-030 |

## Latency Results
| Slice | p50 | p95 | p99 | Sample | Warm/Cold | Notes |
|---|---:|---:|---:|---:|---|---|
| Channel ingress → egress | — | — | — | 0 | — | **Not yet measurable** — the socle runs no live turn. Canonical per-slice spans are emitted by the existing session/ingress/egress probes when the transport is wired into `StreamingVoiceSession` (TASK-WEB-027). Live mouth-to-ear on this path is measured at TASK-WEB-031. |

## Component Findings
| Brick | Status | Findings | Next action |
|---|---|---|---|
| Framing serializer (`WebSocketAudioSerializer`) | PASS | Deterministic demux, no logging (no PII), straight-through PCM16 | Wire into session (WEB-027) |
| Transport socle (`websocket_support`) | PASS | websockets-based, no FastAPI, Origin seam exposed | HAProxy `wss` routing (INFRA-010) |

## Defects And Gaps
| Severity | Finding | Impact | Owner |
|---|---|---|---|
| Low | No live-socket acceptance test (real port bind + client) | AC#1 proven structurally, not over a live connection | Covered by WEB-028 client + WEB-031 QA |

## Open Questions
- Product: none.
- Architecture: none — ADR-0043 spike outcome recorded (socle confirmed).
- Technical: effective `PIPECAT_ALLOWED_ORIGINS` value for the pilot edge → decided at INFRA-010.

## Recommendation
- **Go / No-go:** GO (socle + framing scope). Merge-ready pending the user's explicit merge request.
- **Required fixes before pilot:** none for this ticket; external live path completed by WEB-027/028/031 + INFRA-010.

## Test Evidence
- Unit: `tests/test_websocket_framing.py` (17), `tests/test_websocket_support.py` (6). Full suite **526** green.
- Behave: `features/websocket_transport.feature` (3 scenarios / 11 steps). Full suite **14 features / 39 scenarios / 180 steps** green.
- Adversarial code review: **94/100 — Pass** (allowed_origins seam finding fixed).
