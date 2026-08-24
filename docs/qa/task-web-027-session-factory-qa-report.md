# QA Functional And Latency Report — TASK-WEB-027 (Transport-agnostic session factory)

## Executive Summary
- **Overall readiness:** GO for merge-ready. Both acceptance criteria covered by automated
  tests; the WebRTC path is byte-for-byte (full existing `test_webrtc_signaling.py` passes
  unchanged) and a non-WebRTC stub transport builds the same session via the shared factory.
- **Main blockers:** none.
- **Residual risks:** none new — this is a behaviour-preserving refactor (capitalisation
  lever, ADR-0043 spine point 3). The second live transport (WebSocket) is built on this
  seam at TASK-WEB-028/029; live latency on that path is measured at TASK-WEB-031.

## Scope Tested
- **Epics / stories:** EPIC-006 / TASK-WEB-027 (ADR-0043 transport-agnostic seam,
  ADR-0022/0033 WebRTC session, ADR-0040 future Genesys reuse).
- **Channels:** none live — refactor of the shared session-building core used by every
  transport (WebRTC today; WebSocket + Genesys next).
- **Providers / fakes:** manual fakes only (fake ingress/egress/backend, `SimpleNamespace`
  providers, stub transport exposing `input()`/`output()`). No DB / Ollama / network.
- **Environment:** local `voice-agent/.venv` (Python 3.14.2, pipecat 1.5.0).

## Functional Results
| Area | Status | Evidence | Notes |
|---|---|---|---|
| AC#1 — WebRTC behaviour unchanged after extraction | PASS | `tests/test_webrtc_signaling.py` (27) green unchanged; full suite **530** green | Three tests that poked private building helpers re-pointed at `service._factory` / `web_voice.session_factory` — same assertions, logic simply moved |
| AC#1 — no session-building logic remains WebRTC-specific | PASS | `web_voice/webrtc_signaling.py` keeps only `_build_transport` (WebRTC) + delegation `self._factory.build_session(...)`; assembly lives in `SessionFactory` | Signaling dropped 656 → 389 lines |
| AC#2 — a non-WebRTC transport builds a session through the same factory | PASS | `tests/test_session_factory.py::SessionFactoryStreamingTest` (stub transport → `StreamingVoiceSession` with streaming STT/TTS + farewell) | Same STT/TTS/telemetry/envelope assembly as WebRTC |
| AC#2 — internal audio boundary is PCM16 / 16 kHz | PASS | `tests/test_session_factory.py::SessionFactoryBatchTest` (aggregator `_sample_rate_hz == 16000`, `DEFAULT_SAMPLE_RATE == 16000`) | Codec/sample-rate conversion stays in each transport adapter, never the factory |
| Per-language provider selection preserved (US-042) | PASS | `test_session_factory.py::test_language_selects_the_per_language_provider`; `test_webrtc_signaling.py` language test (via `service._factory`) | Selection moved into the factory intact |

## Latency Results
| Slice | p50 | p95 | p99 | Sample | Warm/Cold | Notes |
|---|---:|---:|---:|---:|---|---|
| Channel ingress → egress | — | — | — | 0 | — | **Not applicable to this ticket** — pure refactor, no runtime behaviour change and no live turn. The same telemetry recorder + session/ingress/egress probes are wired identically (channel-egress probe in `pre_output`, STT/TTS spans unchanged), so all canonical per-slice spans are **preserved**. Live measurement on the new transport is TASK-WEB-031. |

## Component Findings
| Brick | Status | Findings | Next action |
|---|---|---|---|
| `SessionFactory` (`web_voice/session_factory.py`) | PASS | Transport-agnostic; builds streaming + batch session; owns env config (farewell/barge-in/silence/prewarm) + `DEFAULT_SAMPLE_RATE`; class ≈150 lines | Consumed by WebSocket transport (WEB-028/029) |
| `WebRtcSignalingService` | PASS | Keeps only WebRTC transport build + session lifecycle/capacity/farewell wiring; delegates assembly; re-exports moved symbols for backward-compat imports | — |

## Defects And Gaps
| Severity | Finding | Impact | Owner |
|---|---|---|---|
| Info | `# noqa: F401` re-export of moved symbols from `webrtc_signaling` | Kept purely for backward-compat test imports; documented in-code | Acceptable — avoids a churny test rename in the same PR |
| Info | `_build_streaming_session` > 20 lines (kwargs + comments) | Pre-existing style, moved verbatim (was already so in signaling) | No change — not introduced by this refactor |

## Open Questions
- Product: none.
- Architecture: none — ADR-0043 updated with the factory outcome.
- Technical: none.

## Recommendation
- **Go / No-go:** GO. Merge-ready pending the user's explicit merge request.
- **Required fixes before pilot:** none.

## Test Evidence
- Unit: `tests/test_session_factory.py` (3, AC#2); `tests/test_webrtc_signaling.py` (27, AC#1)
  green. Full suite **530** green (527 baseline + 3 new).
- Behave: full suite **14 features / 39 scenarios / 180 steps** green (unchanged — no new
  runtime behaviour).
- Adversarial code review: **95/100 — Pass** (no blocking findings; two Info-level notes).
