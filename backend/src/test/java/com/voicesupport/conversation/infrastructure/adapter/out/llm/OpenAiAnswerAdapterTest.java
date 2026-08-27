package com.voicesupport.conversation.infrastructure.adapter.out.llm;

import com.voicesupport.conversation.domain.model.valueobject.AnswerLanguage;
import com.voicesupport.conversation.domain.model.valueobject.RetrievedEvidence;
import com.voicesupport.shared.observability.BackendTelemetry;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

import java.util.List;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

@DisplayName("OpenAiAnswerAdapter (TASK-BE-033 benchmark candidate)")
class OpenAiAnswerAdapterTest {

    private final OpenAiAnswerAdapter adapter = new OpenAiAnswerAdapter(
            null, new BackendTelemetry(new SimpleMeterRegistry()), 0, 0, 3);

    @Test
    @DisplayName("provider name is 'openai' so telemetry slices are tagged per candidate")
    void provider_name_is_openai() {
        // GIVEN the OpenAI adapter
        // WHEN reading its provider tag
        String provider = adapter.providerName();

        // THEN it is the openai tag used by LlmConfig + BackendTelemetry
        assertEquals("openai", provider);
    }

    @Test
    @DisplayName("system prompt keeps the DEC-002 grounded rules and injects the evidence context")
    void system_prompt_grounds_and_forbids_fabricated_amounts() {
        // GIVEN one evidence chunk
        List<RetrievedEvidence> evidence = List.of(new RetrievedEvidence("chunk-A", "s1", "billing", 0.8));

        // WHEN building the grounded system message in French
        String message = adapter.buildSystemMessage(evidence, List.of(), AnswerLanguage.FRENCH);

        // THEN the DEC-002 rules survive, the context is injected, and the language directive is appended
        assertTrue(message.contains("N'annonce JAMAIS un montant"));
        assertTrue(message.contains("n'invente rien"));
        assertTrue(message.contains("chunk-A"));
        assertFalse(message.contains("{context}"));
        assertTrue(message.contains("répondre UNIQUEMENT en français"));
    }
}
