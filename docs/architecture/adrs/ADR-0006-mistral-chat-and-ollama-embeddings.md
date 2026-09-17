# ADR-0006: Mistral Is Chat LLM, Ollama Remains Embedding Provider

## Status

Accepted — the chat/embedding separation stands; the **default chat provider clause is superseded
by [ADR-0051](ADR-0051-openai-default-llm-wording-provider.md)** (2026-09-17): the default chat LLM
is now OpenAI `gpt-5`, not Mistral. Embeddings are unaffected (still Ollama `nomic-embed-text`, 768).

## Context

The system uses two distinct AI capabilities:

- chat generation for final answers;
- embeddings for knowledge-base vector search.

These capabilities have different models, providers, dimensions, operational
constraints, and migration paths.

## Decision

The chat LLM is selected through the backend LLM ports (DEC-011). At the time of this ADR the
default was Mistral AI (`mistral-small-latest`); **since 2026-09-17 the default is OpenAI `gpt-5`
(ADR-0051)**, with Mistral and Ollama selectable via `LLM_PROVIDER`.

Embeddings remain on local Ollama `nomic-embed-text` with 768 dimensions.

Changing the embedding model is a separate architecture decision because vector
dimensions are persisted in pgvector. Moving to `mistral-embed` or another
embedding model requires updating the configured vector dimension, recreating
the vector table, and re-synchronizing the knowledge base.

## Consequences

- "Switching to Mistral" does not imply switching embeddings.
- Chat provider replacement remains isolated behind LLM ports.
- Embedding replacement has storage migration impact and must not be treated as
  a simple configuration toggle.
- Local embeddings reduce cloud dependency for knowledge ingestion and retrieval.

## Alternatives Considered

- **Use Mistral for both chat and embeddings immediately**: deferred because
  `mistral-embed` uses a different vector dimension and would force vector-store
  recreation.
- **Use Ollama for both chat and embeddings by default**: rejected as the default
  answer path because the target chat quality and cloud benchmark currently
  favor Mistral, while Ollama remains a configurable alternative.

## Related Documents

- `docs/architecture/architecture.md`
- `CLAUDE.md`
- ADR-0039 (tst embeddings placement: Ollama `nomic-embed-text` CPU sidecar)
