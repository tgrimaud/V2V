package com.voicesupport.conversation.infrastructure.adapter.out.llm;

import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

// Same-package test so the protected provider hooks are reachable without reflection. The adapter's
// providerName()/systemPromptTemplate() do not touch the ChatClient or telemetry, so nulls are safe.
@DisplayName("OpenAiAnswerAdapter (provider identity + grounded prompt)")
class OpenAiAnswerAdapterTest {

    private final OpenAiAnswerAdapter adapter = new OpenAiAnswerAdapter(null, null, 8000, 10000, 3);

    @Test
    @DisplayName("reports the openai provider name so telemetry slices are attributable per provider")
    void reportsOpenAiProviderName() {
        // WHEN reading the provider name used for telemetry tagging
        String provider = adapter.providerName();

        // THEN it is the stable 'openai' value (matches voice-support.llm.provider=openai)
        assertEquals("openai", provider);
    }

    @Test
    @DisplayName("uses the grounded DEC-002 voice prompt with a {context} placeholder")
    void usesGroundedDec002Prompt() {
        // WHEN reading the system prompt template
        String prompt = adapter.systemPromptTemplate();

        // THEN it carries the DEC-002 grounding rules and the injectable context placeholder
        assertTrue(prompt.contains("{context}"), "prompt must expose the {context} placeholder");
        assertTrue(prompt.contains("UNIQUEMENT à partir du CONTEXTE"),
                "prompt must forbid ungrounded answers (DEC-002)");
        assertTrue(prompt.contains("N'annonce JAMAIS un montant"),
                "prompt must forbid inventing amounts/prices");
    }
}
