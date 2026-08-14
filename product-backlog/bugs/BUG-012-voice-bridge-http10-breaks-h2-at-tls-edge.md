# BUG-012 — Voice bridge serves HTTP/1.0, breaking HTTP/2 at the HAProxy TLS edge

## Header

- **Bug ID:** BUG-012
- **Title:** Bridge `BaseHTTPRequestHandler` keeps the Python default `HTTP/1.0`; HAProxy cannot mux the 1.0 backend response onto an h2 client → "Empty reply from server" over HTTPS (browser negotiates h2)
- **Status:** Ready for adversarial review
- **Severity:** High
- **Priority:** P1
- **Detected by:** User validation (pilot edge smoke test)
- **Detected date:** 2026-08-14
- **Related user story:** TASK-DEPLOY-002 (voice bridge image) / TASK-INFRA-002 (HAProxy TLS edge)
- **Related epic:** EPIC-012 (V1 pilot deployment)
- **Branch:** fixed inline on `feat/sprint-11-remote-deployment` (found during pilot edge validation)
- **Owner:** Voice runtime developer

## Problem Statement

Loading the voice UI over the HTTPS voice VIP (`https://192.168.0.10:443/`) fails when
the client negotiates HTTP/2 (which every modern browser does, since HAProxy offers
`alpn h2,http/1.1`). HAProxy returns "Empty reply from server". The same request over
HTTP/1.1 returns 200. Root cause: the bridge's HTTP server answers in **HTTP/1.0**.

## Environment

- **Environment:** pilot (eir-ai4cc-tst); voice bridges `vla-ai4cc-t01/t02` (`.103`/`.104:8090`), voice VIP `.10:443` (HAProxy `haproxy:lts-alpine3.23`, 3.4.0)
- **Channel:** web voice (UI + WebRTC signaling over HTTPS)
- **Build or commit:** voice image `0.5.0`; `voice-agent/web_voice/server.py` `build_handler` (no `protocol_version` set)
- **Provider configuration:** HAProxy voice frontend `bind :443 ssl crt … alpn h2,http/1.1`

## Reproduction Steps

1. Given HAProxy fronts the bridges with `alpn h2,http/1.1` and the bridge is healthy.
2. When a client negotiates HTTP/2 over TLS: `curl -sk --http2 https://192.168.0.10:443/`.
3. Then the response is empty (`curl` reports HTTP `000` / "Empty reply from server"),
   while `curl -sk --http1.1 https://192.168.0.10:443/` returns `200`.

## Expected Result

The UI + signaling load over HTTPS regardless of the negotiated ALPN protocol (h2 or
http/1.1), so a normal browser can open `https://<voice VIP>/`.

## Actual Result

Over h2 the browser/curl gets an empty reply and the page fails to load; only an
explicit http/1.1 client works. A direct call to the bridge returns
`HTTP/1.0 200 OK` (`Server: BaseHTTP/0.6 Python/3.12.14`), confirming the 1.0 answer.

## Evidence

- `curl -sk --http2  https://192.168.0.10:443/` → `* Empty reply from server` (HTTP 000).
- `curl -sk --http1.1 https://192.168.0.10:443/` → HTTP 200.
- `curl -sv http://192.168.0.103:8090/` → status line `HTTP/1.0 200 OK`.
- Python `http.server.BaseHTTPRequestHandler.protocol_version` defaults to `HTTP/1.0`.

## Impact

- **Customer / pilot-readiness:** the web voice entry point is unreachable over HTTPS
  from a browser (h2), i.e. the primary pilot access path is down until worked around.
- **Operational:** masqueraded as an HAProxy/TLS problem during edge bring-up, costing
  diagnosis time.
- No security/privacy impact.

## Acceptance Criteria For Fix

- [x] The defect no longer reproduces (bridge answers HTTP/1.1; HAProxy serves h2).
- [x] A regression test covers it (server test asserts the response is HTTP/1.1).
- [x] OpenTelemetry: not applicable (HTTP framing only; no telemetry contract change).
- [ ] Adversarial code review ≥ 90%.
- [ ] QA retest passes (live h2 + browser load over the voice VIP after image redeploy).
- [x] Documentation/backlog updated (this ticket; HAProxy README edge note).

## Developer Notes

- **root cause:** `BaseHTTPRequestHandler` defaults to `HTTP/1.0`; HAProxy's HTX/h2
  mux cannot cleanly translate a 1.0 backend response to an h2 client → empty reply.
- **files changed:** `voice-agent/web_voice/server.py` — set `protocol_version = "HTTP/1.1"`
  on the `WebVoiceHandler` (safe: every bodied response already sends `Content-Length`;
  the only bodiless response is the 204 favicon; no chunked/streaming responses exist).
- **tests added/updated:** `voice-agent/tests/test_web_voice_ingress.py` — assert the
  served response reports HTTP/1.1 (`response.version == 11`).
- **OpenTelemetry added/updated:** n/a.
- **residual risk:** low. HTTP/1.1 keep-alive relies on definite framing, which every
  handler path provides. Requires a voice image rebuild + redeploy to take effect on
  the pilot. Edge alternative (drop `h2` from ALPN) is a platform-side workaround only.

## QA Retest

- **Retested by:** (pending — needs image rebuild + voice tier redeploy)
- **Retest date:** —
- **Scenarios rerun:** local `python -m unittest` (server test) green; live h2 curl +
  browser load over `.10:443` after redeploy.
- **Result:** Local passed; live retest pending redeploy.
- **Retest evidence:** —

## Closure

- **Closed by:** —
- **Closed date:** —
- **Closure reason:** —
