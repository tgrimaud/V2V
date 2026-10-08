package com.voicesupport.conversation.infrastructure.adapter.out.llm;

import com.voicesupport.conversation.domain.model.valueobject.AnswerLanguage;
import com.voicesupport.shared.observability.BackendTelemetry;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.ai.chat.client.ChatClient;
import org.springframework.ai.chat.messages.AssistantMessage;
import org.springframework.ai.chat.messages.Message;
import org.springframework.ai.chat.model.ChatModel;
import org.springframework.ai.chat.model.ChatResponse;
import org.springframework.ai.chat.model.Generation;
import org.springframework.ai.chat.prompt.Prompt;
import reactor.core.publisher.Flux;

import java.util.List;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

// US-043 / TASK-BE-071: the bounded billing clarify LLM step. Drives the REAL adapter over a fake
// ChatModel that captures the Prompt, so the single clarify-turn contract is locked: NO RAG context,
// the per-language clarify directive appended LAST (recency), the history reused, and the raw question
// returned stripped. The orchestration layer (BillingDiagnosticConversationService) enforces the
// trigger/bound and DEC-002 vetting — this test only covers the wording step.
@DisplayName("AbstractChatClientAnswerAdapter.generateClarifyingQuestion (TASK-BE-071)")
class ClarifyingQuestionAdapterTest {

    private final CapturingChatModel model = new CapturingChatModel("Depuis quand remarquez-vous ce souci ?");
    private final SimpleMeterRegistry registry = new SimpleMeterRegistry();
    private final MistralAnswerAdapter adapter =
            new MistralAnswerAdapter(ChatClient.builder(model).build(), new BackendTelemetry(registry), 0, 0, 0);

    @Test
    @DisplayName("returns the model's single question, stripped")
    void returnsStrippedQuestion() {
        String question = adapter.generateClarifyingQuestion(
                "J'ai un souci avec ma facture", List.of(), AnswerLanguage.FRENCH);

        assertEquals("Depuis quand remarquez-vous ce souci ?", question);
    }

    @Test
    @DisplayName("builds an ask-one-question prompt with NO RAG context and the clarify directive LAST")
    void buildsClarifyPromptWithoutContext() {
        adapter.generateClarifyingQuestion("J'ai un souci avec ma facture", List.of(), AnswerLanguage.FRENCH);

        String system = model.lastSystemMessage;
        assertTrue(system.contains("ask ONE short"), "must instruct to ask a single question");
        assertFalse(system.contains("{context}"), "no RAG placeholder");
        assertFalse(system.contains("CONTEXT:"), "the clarify turn has no retrieved context");
        // Recency: the per-language clarify directive is the trailing instruction.
        assertTrue(system.trim().endsWith(AnswerLanguage.FRENCH.clarifyDirective()),
                "the clarify directive must be appended last for recency");
    }

    @Test
    @DisplayName("reuses the conversation history so the question does not repeat an earlier one")
    void reusesHistory() {
        List<String> history = List.of("Client : J'ai un souci avec ma facture",
                "Assistant : Pouvez-vous m'en dire plus ?");

        adapter.generateClarifyingQuestion("Elle a augmenté", history, AnswerLanguage.FRENCH);

        assertTrue(model.lastSystemMessage.contains("Pouvez-vous m'en dire plus ?"),
                "the prior assistant question must be visible so the LLM does not repeat it");
    }

    @Test
    @DisplayName("a null language falls back to English")
    void nullLanguageFallsBackToEnglish() {
        adapter.generateClarifyingQuestion("I have a billing problem", List.of(), null);

        assertTrue(model.lastSystemMessage.trim().endsWith(AnswerLanguage.ENGLISH.clarifyDirective()));
    }

    // Fake ChatModel capturing the last Prompt's system message and returning a fixed question.
    private static final class CapturingChatModel implements ChatModel {
        private final String reply;
        private String lastSystemMessage = "";

        private CapturingChatModel(String reply) {
            this.reply = reply;
        }

        @Override
        public ChatResponse call(Prompt prompt) {
            for (Message message : prompt.getInstructions()) {
                if (message instanceof org.springframework.ai.chat.messages.SystemMessage) {
                    lastSystemMessage = message.getText();
                }
            }
            return new ChatResponse(List.of(new Generation(new AssistantMessage(reply))));
        }

        @Override
        public Flux<ChatResponse> stream(Prompt prompt) {
            return Flux.just(call(prompt));
        }
    }
}
