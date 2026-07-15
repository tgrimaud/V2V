# Development Guide

> **Branch state (`feat/restart-from-scratch`, updated 2026-07-15):** this branch is a
> deliberate restart. The Java backend, React frontend, target Pipecat agent
> (`agent/bot.py`) and legacy bridge (`bridge_server.py`) were removed (preserved on
> `main`). The **only runnable code here is the Python voice slice** under
> `voice-agent/`, which now covers the full **voice-in → backend answer → voice-out**
> loop: STT validation (Sprint 1/2), TTS voice-out (Sprint 3, TASK-WEB-002), a
> **Pipecat batch runtime** since Sprint 4 (TASK-WEB-005, selectable via
> `--runtime {stdlib,pipecat}`, default `pipecat`) and, since Sprint 5
> (TASK-WEB-003 A–G), a real **backend answer bridge** (`--backend {stub,http}`,
> default `stub`) with a safe degraded-mode fallback. There is no streaming/WebRTC
> or barge-in yet (Sprint 6). The "Working On This Branch"
> section below is accurate for this branch. Everything from "## Target V1 Stack"
> onward describes the target stack (reference on `main`) and does **not** run here —
> do not follow those `mvn` / `npm` / `docker compose` / `agent.bot` steps against
> this checkout.

## Working On This Branch (Python voice slice — the only runnable code)

All code lives under `voice-agent/` (Python 3, standard library + `pipecat-ai` for the
batch runtime + `behave` for BDD).
Configuration comes from a repo-root `.env` (copy `.env.example` as a starting point):

```bash
# voice-support-bot/.env
GRADIUM_API_KEY=...          # never commit a real key
GRADIUM_LANGUAGE=fr
GRADIUM_INPUT_FORMAT=pcm_16000
GRADIUM_VOICE_ID=default     # "default" is auto-resolved to the real FR catalog voice
```

Common tasks (run from `voice-agent/`):

```bash
# Unit tests
python3 -m unittest discover -s tests -p 'test_*.py'

# Behave acceptance scenarios (isolated venv)
python3 -m venv .venv && ./.venv/bin/pip install behave
./.venv/bin/behave features/

# (Re)generate the raw PCM16 16 kHz fixtures (macOS `say`)
python3 fixtures/generate_fixtures.py

# Transcription quality (WER) — offline fixture provider, then real Gradium
python3 -m stt_validation.quality_cli fixtures/manifest.json
export $(grep -v '^#' ../.env | xargs) && \
  python3 -m stt_validation.quality_cli fixtures/manifest.json --provider gradium

# Per-pipeline-slice latency report (US-036)
python3 -m stt_validation.pipeline_timing_cli fixtures/manifest.json --provider gradium

# Web voice loop: browser mic -> STT -> backend answer -> TTS -> playback
python3 -m web_voice.server --provider gradium   # then open http://127.0.0.1:8090/
python3 -m web_voice.server --provider fixture   # offline plumbing check (no key)

# Select the conversation backend (default is the offline stub; http targets VOICE_BACKEND_URL)
python3 -m web_voice.server --provider fixture --backend stub
VOICE_BACKEND_URL=http://127.0.0.1:8080/answer python3 -m web_voice.server --provider gradium --backend http

# Select the runtime (default is pipecat; stdlib is the fallback/comparison path)
python3 -m web_voice.server --provider fixture --runtime pipecat
python3 -m web_voice.server --provider fixture --runtime stdlib
VOICE_RUNTIME=stdlib python3 -m web_voice.server --provider fixture

# A/B parity harness: same input through both runtimes (identical WAV + latency)
python3 scripts/ab_parity.py --iterations 20
```

Endpoints: `POST /api/voice/stt` (PCM16 in → transcript JSON), `POST /api/voice/tts`
(`?text=` → WAV), and `POST /api/voice/turn` (PCM16 in → full STT → backend answer →
TTS → WAV in one call, with the transcript + spoken answer returned as `X-Voice-*`
headers). All three keep the same contract on both runtimes.

Troubleshooting (current branch):

| Problem | Cause | Solution |
|---|---|---|
| `GRADIUM_API_KEY not set` | env not loaded | Fill repo-root `.env`, then `export $(grep -v '^#' ../.env \| xargs)` |
| Quality/Behave run finds no audio | `.pcm` fixtures not generated | `python3 fixtures/generate_fixtures.py` (macOS `say`) |
| `No module named behave` | behave not installed | Use the `.venv` shown above |
| Port 8090 busy | web_voice server already running | `kill $(lsof -ti:8090)` |
| WER = 1.0 on a correct transcript | pre-2026-07-10 scorer did not normalize | Fixed — `word_error_rate` now folds case/punctuation/accents (TASK-STT-011, RF-008 Closed) |

See `voice-agent/README.md` for the full harness reference and
`docs/observability/` + `docs/qa/` for evidence.

---

## Target V1 Stack (reference — preserved on `main`, NOT runnable on this branch)

> Everything below describes the intended/previous full stack (Java backend,
> Pipecat agent, React frontend, Docker Compose, pgvector, Ollama). It is kept as
> a build reference for the restart. **None of these commands work against
> `feat/restart-from-scratch`** — the code they target does not exist here.

## Project Conventions

### Architecture

- **Pure domain**: no Spring annotations, no external dependencies in `domain/`
- **IN ports**: use-case interfaces (what the system offers)
- **OUT ports**: dependency interfaces (what the system needs)
- **Adapters**: technical implementations of ports
- **Configuration**: Spring wiring lives in `infrastructure/config/` — domain beans are registered through `@Bean`, never through `@Service`

### Tests

- **No Mockito**: tests use manual fakes (`static` inner classes)
- **Naming**: `shouldVerbSomething` (e.g. `shouldReturnAnswerWithCitations`)
- **Structure**: GIVEN / WHEN / THEN (implicit in the test structure)

### Code Style

- Methods: max 20 lines
- Classes: max 200 lines
- Nesting: max 3 levels
- No Javadoc on ports and models (project convention)
- No obvious comments

## Add a New Provider

### Example: add OpenAI as an alternative LLM

1. Create the adapter (it must implement both ports):

```java
// infrastructure/adapter/out/llm/OpenAILlmAdapter.java
public class OpenAILlmAdapter implements LlmPort, LlmStreamingPort {
    private final ChatClient chatClient;

    @Override
    public String generateAnswer(...) {
        return chatClient.prompt().system(sys).user(q).call().content();
    }

    @Override
    public TokenStream streamAnswer(...) {
        return TokenStream.fromIterable(chatClient.prompt().system(sys).user(q).stream().content().toIterable());
    }
}
```

2. Add the conditional bean (one bean satisfies both interfaces):

```java
// infrastructure/config/DomainServiceConfig.java
@Bean
@ConditionalOnProperty(name = "voice-support.llm.provider", havingValue = "openai")
public OpenAILlmAdapter openAiLlmAdapter(ChatClient chatClient) {
    return new OpenAILlmAdapter(chatClient);
}
```

3. Add the property in `application.yml`:

```yaml
voice-support:
  llm:
    provider: openai  # or mistral-api (default) or ollama
```

### Change the STT/TTS Provider (voice agent)

STT and TTS are handled by the Pipecat agent (Python). To change provider:

1. Modify `voice-agent/pyproject.toml` — change the Pipecat extra:

```toml
dependencies = [
    "pipecat-ai[deepgram,cartesia,websocket,silero]",  # ex: Deepgram STT + Cartesia TTS
]
```

2. Modify the target pipeline `voice-agent/agent/bot.py` — instantiate the right Pipecat service:

```python
from pipecat.services.deepgram import DeepgramSTTService
from pipecat.services.cartesia import CartesiaTTSService

stt = DeepgramSTTService(api_key=os.getenv("DEEPGRAM_API_KEY"))
tts = CartesiaTTSService(api_key=os.getenv("CARTESIA_API_KEY"), voice_id="...")
```

No Java backend change is required — the Pipecat RAG processor keeps calling the
same backend conversation API. If the legacy WebSocket bridge remains used for
comparison, document its STT/TTS adapter separately instead of making it the
target path.

## Add a New Specialist Agent

The multi-agent system is extensible. To add a new agent (e.g. after-sales returns):

1. **Create the KB** in `knowledge-base/sav-faq.md`

2. **Add the profile** in `AgentProfile.java`:

```java
public static AgentProfile sav() {
    return new AgentProfile(
            "sav",
            "Agent SAV",
            """
            You are an after-sales support agent specialized in returns and exchanges...
            Knowledge base context:
            {context}
            """,
            "sav",
            List.of("retour", "échange", "panne matériel", "renvoi", "colis",
                    "garantie", "remplacement", "défectueux")
    );
}
```

3. **Register it** in `DomainServiceConfig.agentRegistry()`:

```java
@Bean
public AgentRegistry agentRegistry() {
    return new AgentRegistry(
            List.of(AgentProfile.support(), AgentProfile.billing(),
                    AgentProfile.commercial(), AgentProfile.sav()),
            "support"
    );
}
```

4. **Ingest the KB** with the domain tag:

```bash
curl -X POST http://localhost:8081/api/knowledge/ingest \
  -F "file=@knowledge-base/sav-faq.md" \
  -F "source=sav-faq.md" \
  -F "domain=sav"
```

No change to the orchestrator, classifier, or adapters is required.

## Add a Document to the Knowledge Base

> See also: [`knowledge-base-technical.md`](../knowledge-base/knowledge-base-technical.md) (KB
> architecture + adding a connector) and [`knowledge-base-guide.md`](../knowledge-base/knowledge-base-guide.md)
> (content writing guide for contributors).

1. Create a Markdown file in `knowledge-base/`:

```markdown
# New Topic

## Section 1

Structured content with paragraphs separated by blank lines.

## Section 2

Each paragraph becomes a potential chunk.
```

2. Ingest through the API with the domain tag (required for multi-agent routing):

```bash
# Technical support
curl -X POST http://localhost:8081/api/knowledge/ingest \
  -F "file=@knowledge-base/telecom-faq.md" \
  -F "source=telecom-faq.md" \
  -F "domain=support"

# Billing
curl -X POST http://localhost:8081/api/knowledge/ingest \
  -F "file=@knowledge-base/billing-faq.md" \
  -F "source=billing-faq.md" \
  -F "domain=billing"

# Commercial
curl -X POST http://localhost:8081/api/knowledge/ingest \
  -F "file=@knowledge-base/commercial-faq.md" \
  -F "source=commercial-faq.md" \
  -F "domain=commercial"
```

The `domain` parameter tags each chunk so vector search can be filtered by agent.
Without `domain`, chunks are stored without a filter (backward-compatible but not recommended).

Chunking respects paragraph boundaries and propagates headings as section metadata.

### Multi-Source Synchronization (recommended)

The `curl ... /ingest` path remains available for one-shot uploads, but the KB is
now fed by synchronized **source connectors**. The reference connector
`MarkdownFolderConnector` reads `knowledge-base/*.md` and resolves `domain` from
the **YAML front-matter** at the top of each file:

```markdown
---
domain: billing
language: fr
---

# Knowledge Base — Billing and Subscriptions
...
```

Trigger a sync manually:

```bash
# All sources
curl -X POST http://localhost:8081/api/knowledge/sync

# One source only (by connector type)
curl -X POST http://localhost:8081/api/knowledge/sync/markdown
```

The response is a report: `{ "processed": 3, "ingested": 3, "skipped": 0, "deleted": 0 }`.
Sync is **idempotent**: an unchanged document (same `content_hash`) is ignored
(`skipped`), a modified document is re-ingested (`deleted`, then re-chunked), and
a document that disappeared from the source is removed from the vector store. Sync
state is stored in the `kb_source_state` table.

A **scheduled** sync runs via cron (`voice-support.knowledge.sync-cron`, hourly
default `0 0 * * * *`). Set `KB_SYNC_CRON=-` to disable it in development.

Migration from the old `curl /ingest` seeding: pre-existing rows have no
`source_id`, so to avoid duplicates, empty the table once before the first sync:
`DELETE FROM vector_store;`, then `POST /api/knowledge/sync`.

## Common Troubleshooting

| Problem | Cause | Solution |
|----------|-------|----------|
| `Unknown type vector` | pgvector extension not enabled | `docker exec <container> psql -U voicesupport -d voicesupport -c "CREATE EXTENSION vector;"` |
| `relation "vector_store" does not exist` | Schema not initialized | Add `initialize-schema: true` in the pgvector config |
| `model 'llama3.1' not found` | Wrong model tag | Use `llama3.1:8b` (check with `ollama list`) |
| Port 8081 busy | Another instance is running | `kill $(lsof -ti:8081)` |
| Port 7860 busy | Pipecat agent already running | `kill $(lsof -ti:7860)` |
| Port 8765/8766 busy | Legacy custom bridge already running | `kill $(lsof -ti:8765)` |
| Slow ingestion | Ollama generates embeddings | Normal on first call (~1s/chunk), then cached |
| Pipecat UI unavailable | Runner not started | `cd voice-agent && python -m agent.bot -t webrtc`, then open `http://localhost:7860` |
| Legacy React frontend does not connect to the voice agent | Wrong URL | Check `VITE_VOICE_AGENT_URL=ws://localhost:8765` |
| `GRADIUM_API_KEY not set` | Missing variable | `cp voice-agent/.env.example voice-agent/.env` and configure it |
| `Embeddings not found for default` | Invalid `GRADIUM_VOICE_ID` | Use a real ID from the [catalog](https://docs.gradium.ai/guides/voices/all-voices) (e.g. `b35yykvVppLXyw_l` for Elise FR) |
| Legacy browser TTS audio not played | Raw PCM cannot be decoded by `decodeAudioData` | The legacy bridge must wrap PCM in a WAV header (44 bytes) before sending |
| Pipecat agent does not start | Missing dependencies | `cd voice-agent && uv pip install -e .` |
| VAD loads `silero_vad_legacy.onnx` | Wrong default model | Add `model: 'v5'` in `MicVAD.new()` options |
| VAD `Can't create a session` | Missing ONNX file in `public/` | Copy `node_modules/@ricky0123/vad-web/dist/silero_vad_v5.onnx` and `vad.worklet.bundle.min.js` into `frontend/public/` |
| VAD does not detect speech | `startOnLoad: true` + React double mount | Add `startOnLoad: false` and call `vad.start()` manually |
| Barge-in does not cut off the bot | Wrong voice path launched | Use Pipecat (`python -m agent.bot -t webrtc`) for the V1 target, or restart the legacy bridge |
| `401 Unauthorized` from Mistral | API key not loaded | Start the backend with `export $(cat backend/.env \| xargs) && mvn spring-boot:run` or source `.env` first |
| Bot answers off-topic on "Bonjour" | Guardrails not active | Check that `GuardrailService` is in `DomainServiceConfig` and restart the backend |
| Bot repeats the greeting on the 1st Pipecat message | The greeting played by TTS is not in backend history | `bot.py` must call `POST /api/conversation/seed` on `on_client_connected`; restart the voice agent after updating |
| Multi-agent routing does not work | KB not tagged | Re-ingest with the `domain=support\|billing\|commercial` parameter |
| Generic answers despite routing | Chunks without a domain in DB | Empty the table and re-ingest: `DELETE FROM vector_store;`, then re-run curl ingest |

## Useful Commands

```bash
# Check service status
curl http://localhost:8081/api/health
docker compose ps

# Start the local stack, including the V1 Pipecat WebRTC agent
docker compose up --build pipecat-agent backend frontend

# Install VAD assets after npm install
cp node_modules/@ricky0123/vad-web/dist/silero_vad_v5.onnx frontend/public/
cp node_modules/@ricky0123/vad-web/dist/vad.worklet.bundle.min.js frontend/public/

# Start the Java backend (load .env for the Mistral key)
cd backend && export $(cat .env | xargs) && mvn spring-boot:run

# Start the V1 target voice agent (Pipecat + Gradium)
# Web (WebRTC) + prebuilt UI at http://localhost:7860
cd voice-agent && python -m agent.bot -t webrtc
# All transports (web + telephony):
cd voice-agent && python -m agent.bot
# Pipecat telephony (requires a public proxy, e.g. ngrok):
cd voice-agent && python -m agent.bot -t twilio -x <your-public-host>

# Start the legacy/fallback custom bridge (React :5173, ws:8765/8766)
cd voice-agent && python -u -m agent.bridge_server

# Test SSE streaming (token-by-token response)
curl -N "http://localhost:8081/api/conversation/ask-stream?question=Hello&conversation_id=test"

# Seed history with the greeting (used by the Pipecat bot)
# to prevent the LLM from greeting again on the 1st user message
curl -X POST http://localhost:8081/api/conversation/seed \
  -H "Content-Type: application/json" \
  -d '{"message": "Hello! I am your virtual assistant.", "conversation_id": "test"}'

# Test RAG (synchronous mode)
curl -s -X POST http://localhost:8081/api/conversation/ask \
  -H "Content-Type: application/json" \
  -d '{"question": "My router no longer works", "conversation_id": "test"}' | python3 -m json.tool

# Measure time-to-first-byte (streaming latency)
curl -w "\nTTFB: %{time_starttransfer}s\nTotal: %{time_total}s\n" -s -o /dev/null \
  "http://localhost:8081/api/conversation/ask-stream?question=Hello&conversation_id=perf"

# View indexed chunks
docker exec voice-support-bot-postgres-1 psql -U voicesupport -d voicesupport \
  -c "SELECT id, substring(content, 1, 80) FROM vector_store LIMIT 10;"

# Empty the knowledge base (re-ingestion)
docker exec voice-support-bot-postgres-1 psql -U voicesupport -d voicesupport \
  -c "DELETE FROM vector_store;"

# View admin stats
curl -s http://localhost:8081/api/admin/stats | python3 -m json.tool

# Test escalation
curl -s -X POST http://localhost:8081/api/conversation/ask \
  -H "Content-Type: application/json" \
  -d '{"question": "I want to cancel"}' | python3 -m json.tool

# Test guardrails — greeting (no RAG)
curl -s -X POST http://localhost:8081/api/conversation/ask \
  -H "Content-Type: application/json" \
  -d '{"question": "Hello", "conversation_id": "test"}' | python3 -m json.tool

# Test guardrails — off-topic
curl -s -X POST http://localhost:8081/api/conversation/ask \
  -H "Content-Type: application/json" \
  -d '{"question": "What is the weather outside?", "conversation_id": "test"}' | python3 -m json.tool

# Test multi-agent routing — billing
curl -s -X POST http://localhost:8081/api/conversation/ask \
  -H "Content-Type: application/json" \
  -d '{"question": "How can I view my invoice?", "conversation_id": "test-billing"}' | python3 -m json.tool

# Test multi-agent routing — commercial
curl -s -X POST http://localhost:8081/api/conversation/ask \
  -H "Content-Type: application/json" \
  -d '{"question": "I am moving, how can I transfer my subscription?", "conversation_id": "test-commercial"}' | python3 -m json.tool

# Ingest the 3 KBs with domains (after a reset)
curl -X POST http://localhost:8081/api/knowledge/ingest -F "file=@knowledge-base/telecom-faq.md" -F "source=telecom-faq.md" -F "domain=support"
curl -X POST http://localhost:8081/api/knowledge/ingest -F "file=@knowledge-base/billing-faq.md" -F "source=billing-faq.md" -F "domain=billing"
curl -X POST http://localhost:8081/api/knowledge/ingest -F "file=@knowledge-base/commercial-faq.md" -F "source=commercial-faq.md" -F "domain=commercial"

# Stop everything
docker compose down
kill $(lsof -ti:8081) 2>/dev/null
kill $(lsof -ti:8765) 2>/dev/null
```

## Latency Measurement (baseline)

The critical path is instrumented with structured logs prefixed by `[LATENCY]`,
without any additional dependency. Each step emits a
`[LATENCY] step=<name> ms=<value> [extra...]` line:

| Step (`step`) | Emitted by | File |
|----------------|----------|---------|
| `stt` | Voice agent | `voice-agent/agent/gradium_stt.py` |
| `vector_search` | Backend | `PgVectorStoreAdapter` |
| `llm_first_token` / `llm_total` | Backend | `MistralLlmAdapter` / `OllamaLlmAdapter` |
| `tts` | Voice agent | `voice-agent/agent/gradium_tts.py` |
| `time_to_first_audio` | Voice agent | legacy `bridge_server.py` or Pipecat metrics depending on the tested path |
| `turn_total` | Voice agent | legacy `bridge_server.py` or Pipecat metrics depending on the tested path |

Per
[`ADR-0018`](../architecture/adrs/ADR-0018-voice-latency-targets-and-slo-measurement.md),
the current pilot acceptance criterion is `time_to_first_audio` p95 < 800 ms in
a pre-warmed, co-located environment. The ~700 ms value is an aspirational
user-experience target; production SLOs remain deferred until ADR-0010
observability and degraded-mode gates are met.

### Capture and Aggregate a Baseline

```bash
# 1. Capture service logs during a Pipecat session
cd backend && export $(cat .env | xargs) && mvn spring-boot:run 2>&1 | tee /tmp/backend.log
cd voice-agent && python -m agent.bot -t webrtc 2>&1 | tee /tmp/pipecat.log

# 2. Run a few representative voice exchanges (10-20 turns)

# 3. Aggregate p50/p95 by step
python voice-agent/tools/latency_report.py /tmp/backend.log /tmp/pipecat.log
```

The report shows `n / p50 / p95 / min / max / mean` by step and marks the
`time_to_first_audio` pilot criterion as `OK`/`FAIL`. Record the channel,
environment, provider configuration, and whether caches/connections were warm.
The legacy bridge can be launched separately for comparison, but the V1 baseline
must start from Pipecat.
