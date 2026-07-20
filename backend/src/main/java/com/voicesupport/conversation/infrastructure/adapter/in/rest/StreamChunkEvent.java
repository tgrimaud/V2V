package com.voicesupport.conversation.infrastructure.adapter.in.rest;

// SSE `chunk` event payload (ADR-0013): one guardrail-vetted, safe-to-voice sentence. Serialized
// snake_case via the global Jackson config.
public record StreamChunkEvent(String text) {
}
