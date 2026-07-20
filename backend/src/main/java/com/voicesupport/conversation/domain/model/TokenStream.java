package com.voicesupport.conversation.domain.model;

import com.voicesupport.conversation.domain.model.valueobject.GeneratedAnswer;

import java.util.function.Consumer;

// Domain streaming contract (ADR-0013). Consuming the stream drives the guarded, sentence-level
// pipeline: each safe (guardrail-vetted) chunk is delivered to onChunk in order, and the terminal
// GeneratedAnswer (grounded text + confidence, or a safe fallback) is returned when the stream
// ends. Kept free of any reactive/framework type so the domain stays pure; the infrastructure
// adapter is responsible for confining the provider's reactive stream.
@FunctionalInterface
public interface TokenStream {

    GeneratedAnswer consume(Consumer<String> onChunk);
}
