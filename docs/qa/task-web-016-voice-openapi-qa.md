# QA Functional And Latency Report — TASK-WEB-016 (Voice-runtime OpenAPI spec)

## Executive Summary
- **Overall readiness:** Go. The Python voice runtime now publishes a hand-written
  OpenAPI 3.0.3 description of its full `/api/voice/*` surface, served at
  `GET /api/voice/openapi.yaml`, and it passes independent OpenAPI schema validation.
- **Main blockers:** none.
- **Residual risks:** the spec is hand-maintained (the runtime has no framework to
  auto-generate it). Mitigated by an automated **drift guard** that fails if a route is
  added/removed without updating the spec, plus the contract doc remaining the source of
  truth. A field-level drift inside an existing endpoint (e.g. a new header) is not
  caught automatically and stays a review responsibility.

## Scope Tested
- **Ticket:** TASK-WEB-016 — OpenAPI spec for the Python voice runtime (`web_voice`).
- **Epics / stories:** EPIC-006 (Voice2Voice), cross-cutting API hardening; paired with
  TASK-BE-016 (backend OpenAPI).
- **Channels:** web voice runtime HTTP surface (batch loop + WebRTC signaling seam).
- **Providers / fakes:** fixture STT/TTS + stub backend for the running server; no cloud
  provider needed (spec/serve surface only).
- **Environment:** local, `voice-agent/.venv` (Python 3.14.2), `--runtime stdlib
  --backend stub --webrtc off`, warm.

## Functional Results
| Area | Status | Evidence | Notes |
|---|---|---|---|
| Valid OpenAPI 3 document | ✅ Pass | `openapi-spec-validator` validates `web_voice/openapi.yaml` (3.0.3) — no schema errors | Independent industry-standard validator, not just structural asserts |
| Every `web_voice` endpoint documented | ✅ Pass | 5 paths: `stt`, `tts`, `turn`, `webrtc/offer`, `openapi.yaml` | Matches the server's route constants exactly |
| Params / bodies / responses described | ✅ Pass | `audio/pcm` in, `audio/wav` out; query envelope (`conversation_id`/`session_id`/`correlation_id`/`language`); `/turn` `X-Voice-*`/`X-Answer-*` headers incl. degraded contract | Verified 1:1 against `server.py` |
| Error contract described | ✅ Pass | `VoiceErrorBody` (client-safe: `outcome`/`error_code`/`correlation_id`/`message`) + `GuardError` (size/route/webrtc); 413/502/503 with exact codes (`audio_too_large`, `text_too_large`, `webrtc_unavailable`, `webrtc_negotiation_failed`) | Guards match: 25 MiB audio, 5000-char text |
| Correlation-id surfaced | ✅ Pass | `/turn` documents `X-Correlation-Id`; envelope `correlation_id` param on every endpoint | Consistent with backend TASK-BE-016 header docs |
| Spec matches the HTTP contract doc | ✅ Pass | `docs/architecture/voice-runtime-http-contract.md` now links the mirror; values cross-checked against `server.py` | Contract doc stays authoritative |
| Drift caught in review (automated) | ✅ Pass | `tests/test_voice_openapi.py::test_spec_does_not_drift_from_the_servers_actual_routes` + Behave "describes every voice endpoint the server exposes" | Path-set drift is now a test failure, not a review miss |
| Served for discovery/tooling | ✅ Pass | Live: `200`, `Content-Type: application/yaml; charset=utf-8`, 13 629 bytes; live-served bytes re-validated as OpenAPI 3.0.3 | `Content-Length` set; missing-file → 404 JSON |
| No secret/PII leak in the spec | ✅ Pass | Spec documents only client-safe fields; error body explicitly excludes provider text/paths (RF-013) | Same policy as the running server |

## Latency Results
| Slice | p50 | p95 | p99 | Sample | Warm/Cold | Notes |
|---|---:|---:|---:|---:|---|---|
| — | — | — | — | — | — | **Not applicable.** This is a static meta/discovery route (serves a committed YAML file); it is not part of the Voice2Voice journey and maps to no pilot latency slice (ADR-0018). No runtime pipeline behavior changed. |

## Component Findings
| Brick | Status | Findings | Next action |
|---|---|---|---|
| `web_voice/openapi.yaml` (spec) | ✅ Pass | Valid OpenAPI 3.0.3; complete endpoint/param/response/error coverage | Keep in sync with the contract doc on every route change |
| `web_voice/server.py` `_serve_openapi` | ✅ Pass | Fixed constant path (no traversal), correct content-type + length, 404 fallback | None |
| Regression net | ✅ Pass | unittest 390 green (5 spec tests incl. drift + live serve); behave 30 scenarios / 140 steps green (+1 discovery scenario) | None |

## Defects And Gaps
| Severity | Finding | Impact | Owner |
|---|---|---|---|
| Low | Drift guard covers the path set, not per-endpoint field drift (new header/param inside an existing route) | A stale field could go undocumented without a test failure | Review discipline; contract doc is source of truth |

## Open Questions
- **Product:** none.
- **Architecture:** none — spec mirrors the existing contract doc and ADR-0002/0021.
- **Technical:** none. (Auth is intentionally absent on the pilot host; identity is
  gated by OQ-001 / RF-006 and documented as such in the spec description.)

## Recommendation
- **Go / No-go:** **Go.** Both acceptance criteria met — a valid OpenAPI document
  describes every endpoint, and drift vs the contract/server is caught automatically.
- **Required fixes before pilot:** none. When the runtime gains/removes a route or
  changes a field, update `openapi.yaml` in the same change (the path-set drift guard
  will fail otherwise; field changes remain a review item).
