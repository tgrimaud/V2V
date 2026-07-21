package com.voicesupport.conversation.infrastructure.adapter.out.llm;

import com.voicesupport.conversation.domain.model.valueobject.AnswerLanguage;
import com.voicesupport.conversation.domain.model.valueobject.RetrievedEvidence;
import com.voicesupport.shared.observability.BackendTelemetry;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

import java.util.List;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

@DisplayName("AbstractChatClientAnswerAdapter (grounded system message)")
class AbstractChatClientAnswerAdapterTest {

    private final TestAdapter adapter = new TestAdapter();

    @Test
    @DisplayName("evidence text is injected in place of the {context} placeholder")
    void injectsContext() {
        // GIVEN two evidence chunks
        List<RetrievedEvidence> evidence = List.of(
                new RetrievedEvidence("chunk-A", "s1", "billing", 0.8),
                new RetrievedEvidence("chunk-B", "s2", "billing", 0.7));

        // WHEN building the system message
        String message = adapter.systemMessage(evidence, List.of());

        // THEN the placeholder is replaced with the joined evidence text
        assertTrue(message.contains("chunk-A\n---\nchunk-B"));
        assertFalse(message.contains("{context}"));
    }

    @Test
    @DisplayName("conversation history is appended only when present")
    void appendsHistoryConditionally() {
        // GIVEN a history
        List<String> history = List.of("USER: bonjour", "ASSISTANT: bonjour");

        // WHEN building with and without history
        String withHistory = adapter.systemMessage(List.of(new RetrievedEvidence("ctx", "s", "d", 0.9)), history);
        String withoutHistory = adapter.systemMessage(List.of(new RetrievedEvidence("ctx", "s", "d", 0.9)), List.of());

        // THEN only the first carries the history block
        assertTrue(withHistory.contains("USER: bonjour\nASSISTANT: bonjour"));
        assertFalse(withoutHistory.contains("Historique de la conversation"));
    }

    @Test
    @DisplayName("the answer-language directive is appended per call (TASK-BE-015)")
    void appendsLanguageDirective() {
        // GIVEN one evidence chunk
        List<RetrievedEvidence> evidence = List.of(new RetrievedEvidence("ctx", "s", "d", 0.9));

        // WHEN building for English and for French
        String english = adapter.systemMessage(evidence, List.of(), AnswerLanguage.ENGLISH);
        String french = adapter.systemMessage(evidence, List.of(), AnswerLanguage.FRENCH);

        // THEN each carries the matching forceful language directive
        assertTrue(english.contains("You MUST answer ONLY in English"));
        assertTrue(english.contains("I'll transfer you to an advisor"));
        assertTrue(french.contains("répondre UNIQUEMENT en français"));
        assertTrue(french.contains("je vous transfère à un conseiller"));
    }

    private static final class TestAdapter extends AbstractChatClientAnswerAdapter {
        TestAdapter() {
            super(null, new BackendTelemetry(new SimpleMeterRegistry()), 0);
        }

        String systemMessage(List<RetrievedEvidence> evidence, List<String> history) {
            return buildSystemMessage(evidence, history, AnswerLanguage.ENGLISH);
        }

        String systemMessage(List<RetrievedEvidence> evidence, List<String> history, AnswerLanguage language) {
            return buildSystemMessage(evidence, history, language);
        }

        @Override
        protected String systemPromptTemplate() {
            return "Prompt de test.\nCONTEXTE :\n{context}";
        }

        @Override
        protected String providerName() {
            return "test";
        }
    }
}
