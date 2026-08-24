package com.voicesupport.knowledge.infrastructure.adapter.out.health;

import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.boot.actuate.health.Health;
import org.springframework.boot.actuate.health.Status;

import java.net.UnknownHostException;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;

@DisplayName("OllamaEmbeddingHealthAdapter (BUG-014 embedding-hop readiness)")
class OllamaEmbeddingHealthAdapterTest {

    @Test
    @DisplayName("reports UP when the embedding hop probe succeeds")
    void reportsUpWhenProbeSucceeds() {
        // GIVEN a probe that reaches Ollama without error
        OllamaEmbeddingHealthAdapter adapter = new OllamaEmbeddingHealthAdapter(() -> { });

        // WHEN health is evaluated
        Health health = adapter.health();

        // THEN the hop is UP
        assertEquals(Status.UP, health.getStatus());
        assertEquals("embedding/ollama", health.getDetails().get("hop"));
    }

    @Test
    @DisplayName("reports DOWN (so HAProxy drains the node) when the ollama name cannot be resolved")
    void reportsDownOnUnknownHost() {
        // GIVEN a probe failing exactly like BUG-014 (UnknownHostException: ollama)
        OllamaEmbeddingHealthAdapter adapter =
                new OllamaEmbeddingHealthAdapter(() -> { throw new UnknownHostException("ollama"); });

        // WHEN health is evaluated
        Health health = adapter.health();

        // THEN the hop is DOWN and only the exception class name is exposed (no host/path detail)
        assertEquals(Status.DOWN, health.getStatus());
        assertEquals("embedding/ollama", health.getDetails().get("hop"));
        assertEquals("UnknownHostException", health.getDetails().get("error"));
        assertFalse(String.valueOf(health.getDetails().get("error")).contains("ollama"),
                "error detail must not leak the probed host");
    }
}
