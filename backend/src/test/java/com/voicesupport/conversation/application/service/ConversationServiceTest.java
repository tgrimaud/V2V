package com.voicesupport.conversation.application.service;

import com.voicesupport.conversation.domain.model.valueobject.ConversationTurn;
import com.voicesupport.conversation.domain.model.valueobject.GeneratedAnswer;
import com.voicesupport.conversation.domain.port.in.AnswerQuestionUseCase;
import com.voicesupport.conversation.infrastructure.adapter.out.memory.InMemoryConversationMemoryAdapter;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

import java.util.List;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

@DisplayName("ConversationService (memory + history + greeting derivation)")
class ConversationServiceTest {

    private RecordingAnswerUseCase answerUseCase;
    private InMemoryConversationMemoryAdapter memory;
    private ConversationService service;

    @BeforeEach
    void setUp() {
        answerUseCase = new RecordingAnswerUseCase();
        memory = new InMemoryConversationMemoryAdapter(6, 100);
        service = new ConversationService(answerUseCase, memory);
    }

    @Test
    @DisplayName("first turn: empty history, not greeted, all-domain retrieval (domain null, topK 4)")
    void firstTurn() {
        // WHEN the first turn of a conversation is answered
        service.converse("Bonjour", "c1");

        // THEN no prior history is passed and greeting is allowed
        assertTrue(answerUseCase.lastHistory.isEmpty());
        assertFalse(answerUseCase.lastAlreadyGreeted);
        assertNull(answerUseCase.lastDomain);
        assertEquals(4, answerUseCase.lastTopK);
    }

    @Test
    @DisplayName("second turn passes the prior turn as history (current turn excluded) and marks greeted")
    void secondTurnUsesPriorContext() {
        // GIVEN a first completed turn
        answerUseCase.nextAnswer = GeneratedAnswer.grounded("La proration explique l'écart.", 0.8);
        service.converse("Pourquoi ma facture change ?", "c1");

        // WHEN a follow-up is asked
        service.converse("Et le mois prochain ?", "c1");

        // THEN the prior turn is in the history, the current question is not, and greeting is off
        assertTrue(answerUseCase.lastAlreadyGreeted);
        assertEquals(List.of(
                "Client : Pourquoi ma facture change ?",
                "Assistant : La proration explique l'écart."), answerUseCase.lastHistory);
        assertFalse(answerUseCase.lastHistory.contains("Client : Et le mois prochain ?"));
    }

    @Test
    @DisplayName("the completed turn (transcript + produced answer) is recorded in memory")
    void recordsCompletedTurn() {
        // GIVEN the LLM produced a specific answer
        answerUseCase.nextAnswer = GeneratedAnswer.grounded("Réponse groundée.", 0.9);

        // WHEN answering
        service.converse("Ma question", "c1");

        // THEN memory holds exactly that exchange
        List<ConversationTurn> turns = memory.recentTurns("c1");
        assertEquals(1, turns.size());
        assertEquals("Ma question", turns.get(0).userText());
        assertEquals("Réponse groundée.", turns.get(0).assistantText());
    }

    @Test
    @DisplayName("a missing conversation id is stateless: no history in, nothing recorded")
    void blankConversationIdIsStateless() {
        // WHEN two turns are answered without a conversation id
        service.converse("Première question", "");
        service.converse("Deuxième question", "");

        // THEN neither turn sees prior history nor is flagged greeted (no shared bucket)
        assertTrue(answerUseCase.lastHistory.isEmpty());
        assertFalse(answerUseCase.lastAlreadyGreeted);
        // AND nothing is persisted under the blank id
        assertTrue(memory.recentTurns("").isEmpty());
    }

    @Test
    @DisplayName("conversations are isolated: one conversation's history never leaks into another")
    void conversationsAreIsolated() {
        // GIVEN a turn recorded on c1
        service.converse("Question A", "c1");

        // WHEN a first turn is asked on c2
        service.converse("Question B", "c2");

        // THEN c2 saw no history and was not greeted
        assertTrue(answerUseCase.lastHistory.isEmpty());
        assertFalse(answerUseCase.lastAlreadyGreeted);
    }

    // Records what the answer pipeline received; returns a configurable canned answer.
    static class RecordingAnswerUseCase implements AnswerQuestionUseCase {
        GeneratedAnswer nextAnswer = GeneratedAnswer.grounded("ok", 0.7);
        List<String> lastHistory = List.of();
        boolean lastAlreadyGreeted;
        String lastDomain = "unset";
        int lastTopK = -1;

        @Override
        public GeneratedAnswer answer(String question, String domain, int topK, boolean alreadyGreeted,
                                      List<String> history) {
            this.lastDomain = domain;
            this.lastTopK = topK;
            this.lastAlreadyGreeted = alreadyGreeted;
            this.lastHistory = List.copyOf(history);
            return nextAnswer;
        }
    }
}
