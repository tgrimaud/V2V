# ADR-0053: Retire The Interim `:8091` WebSocket Transport And The `stdlib` Server Mode

## Status

Proposed (2026-09-24). **Completes** [ADR-0047](ADR-0047-single-async-http-websocket-server-one-port.md)
(single async HTTP+WebSocket server on one port — shipped as the pilot default in `v0.7.0`) by
retiring the transitional pieces ADR-0047 left in place: the interim single-client
`SingleClientWebsocketServerTransport` on `:8091` (introduced by
[ADR-0043](ADR-0043-interim-websocket-audio-transport-genesys-ready.md)) and the legacy
`--server stdlib` `ThreadingHTTPServer` mode (a survivor of
[ADR-0022](ADR-0022-webrtc-transport-for-streaming-voice-loop.md)). **Supersedes** the
"interim/fallback" status those two ADRs gave those components. Implemented by **TASK-WEB-048**.

## Context

ADR-0047 unified the voice runtime onto a single aiohttp async server (`--server aiohttp`, the
default) serving the UI, `/api/voice/*` REST, WebRTC signaling, the live `/ws` WebSocket audio
transport and the Genesys `/genesys/audiohook` endpoint on one routed port (`:8090`). It is the
**shipped pilot path**: the bridge container `ENTRYPOINT` runs `python -m web_voice.server`
with no `--server` flag → default `aiohttp` (`web_voice/server.py:main`).

ADR-0047 left two transitional components in the tree:

1. **The interim `:8091` WebSocket path** — `web_voice/websocket_signaling.py`
   (`WebSocketSignalingService`) driving Pipecat's `SingleClientWebsocketServerTransport` on a
   second port (`VOICE_WS_PORT`, default `8091`). It is started **only** in `--server stdlib`
   mode (`server.py:main` else-branch); in `aiohttp` mode it is explicitly **not** started.
2. **The `stdlib` server mode** — the legacy `ThreadingHTTPServer` (`WebVoiceHTTPServer` +
   `build_handler`) selected by `--server stdlib`. Its only capability beyond the aiohttp server
   was hosting the interim `:8091` WS (WebRTC signaling and the REST/UI already run under aiohttp
   too).

Two facts make these transitional pieces a net liability now:

- **Dual-maintenance divergence, demonstrated by BUG-026.** Every runtime behaviour (answer-
  language lock, barge-in, end-of-turn, farewell, telemetry names) must be kept in sync across
  **two** WS transports. The interim path already **diverged**: it cannot lock the UI-selected
  answer language because its envelope is built in `start()` **before** the client connects
  (the client's `?language=` is only known in `_on_client_connected`), so it stays on the
  server default. BUG-026's fix therefore only applies to the aiohttp path; the interim path is
  a latent source of the same class of bug.
- **The interim path is the *heavier* one, not a lighter fallback.** It requires the extra
  `websockets` package, is capped at **one client per listener**, and opens a **second port**
  to expose/secure. The aiohttp `/ws` transport rides aiohttp (already transitive via
  pipecat/aiortc), needs **no** extra package, serves **N** clients, and shares one port. The
  original ADR-0022 rationale for a stdlib "no-FastAPI" server is now fully served by aiohttp
  with fewer dependencies — FastAPI was never adopted.

Pipecat is **not** removed by this change: both WS paths are pipecat pipelines; only the
*transport* differs. The pilot path keeps the pipecat pipeline behind the aiohttp-native
`AiohttpWebsocketTransport` (`web_voice/websocket_app.py`), and the transport-agnostic
`SessionFactory` (ADR-0043) is unchanged.

## Decision

Retire both transitional components and make the aiohttp single-port server the **sole** runtime:

1. **Remove the interim `:8091` WS transport**: `web_voice/websocket_signaling.py`
   (`WebSocketSignalingService`, `ws_host_config`, `ws_port_config`, `ws_max_sessions_config`)
   and `web_voice/websocket_support.py` (the `SingleClientWebsocketServerTransport` probe).
2. **Remove the `--server stdlib` mode** and its legacy HTTP server (`WebVoiceHTTPServer`,
   `build_handler`), and drop the `--server` choice (aiohttp becomes implicit/sole). Keep
   `--websocket off` as the only WS on/off gate.
3. **Extract the shared symbols** currently exported from `websocket_signaling.py` and consumed
   by the aiohttp path into a neutral module (the telemetry event/metric name constants
   `SESSION_STARTED_EVENT`, `CLIENT_CONNECTED_EVENT`, `CLIENT_DISCONNECTED_EVENT`,
   `SESSION_REJECTED_EVENT`, `ACTIVE_SESSIONS_METRIC`, `WS_MAX_SESSIONS_ENV_VAR`, and
   `ws_language_config`). Repoint `web_voice/websocket_app.py` and `web_voice/server.py`
   imports. No behaviour change — names and values are preserved.
4. **Tests / behave**: remove `tests/test_websocket_signaling.py`; re-point (or retire) the
   behave capacity feature (`features/steps/websocket_capacity_steps.py`) to the aiohttp `/ws`
   ceiling, which is already unit-covered
   (`test_websocket_app.py::test_over_capacity_connection_is_refused_with_ws_1013`).
5. **Deploy**: drop the `:8091` publish, `VOICE_WS_PORT`, and any `firewall_extra_ports:[8091]`
   from compose/Ansible (already flagged by the ADR-0047 spike README). The Dockerfile
   `ENTRYPOINT` is unchanged (already aiohttp default). Verify `websockets` is only removed from
   `requirements.txt` if nothing else (incl. pipecat) needs it transitively — otherwise leave it.

The change is **transport/plumbing only**: the pipecat pipeline, the `SessionFactory`
(ADR-0043), the backend conversation contract, and the batch `/api/voice/turn` contract are all
unchanged.

## Consequences

- **Single WS transport to maintain** — runtime behaviours (language lock, barge-in, EOT,
  farewell, telemetry) live in exactly one place; the BUG-026 class of divergence disappears.
- **Fewer moving parts** — one server, one port, no `websockets`-package requirement for the
  server, no second port to secure. Aligns the code with the ADR-0047 destination and the
  ADR-0038 edge simplification (the `voice_ws` ACL/backend + `firewall_extra_ports` were already
  slated for removal).
- **Loss of the `stdlib` fallback server mode.** Mitigation: the aiohttp path is the validated
  pilot path since `v0.7.0`; rollback safety comes from release tags / image tags, not a
  second in-tree server. If a no-`aiohttp` environment ever reappears, restore from history.
- **Behave capacity coverage** shifts from the interim service to the aiohttp `/ws` ceiling
  (already unit-tested), keeping the QA contract.
- **Migration impact**: any tooling/doc referencing `VOICE_WS_PORT`, `:8091`, or
  `--server stdlib` must be updated; grep-swept in TASK-WEB-048.

## Alternatives Considered

- **Keep it as-is (fallback, undocumented).** Rejected: leaves the demonstrated dual-maintenance
  divergence (BUG-026) and a misleading "fallback" that is actually heavier and capped at one
  client.
- **Keep but freeze (ADR marking it a non-parity path).** Rejected: still pays the compile/test
  surface and confuses contributors ("why two WS paths?"), for a mode the pilot never runs.
- **Keep and bring to parity** (lazily build the interim envelope at connect time to support the
  language lock). Rejected: spends effort hardening a transitional, single-client, extra-
  dependency path that ADR-0047 already replaced — the opposite of the intended simplification.

## Related Documents

- [ADR-0047](ADR-0047-single-async-http-websocket-server-one-port.md) — single async server on one port (the destination this ADR completes).
- [ADR-0043](ADR-0043-interim-websocket-audio-transport-genesys-ready.md) — introduced the interim `:8091` transport + the transport-agnostic session factory (reused unchanged).
- [ADR-0022](ADR-0022-webrtc-transport-for-streaming-voice-loop.md) — original stdlib `http.server` / "no FastAPI" decision (its stdlib-server clause is retired here).
- [ADR-0046](ADR-0046-websocket-primary-live-voice-transport.md) — WebSocket is the primary live transport.
- BUG-026 — UI language-selector session lock; the concrete divergence that motivates this retirement.
- TASK-WEB-048 — implementation ticket.
