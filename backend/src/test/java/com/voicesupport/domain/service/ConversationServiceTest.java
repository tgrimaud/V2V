package com.voicesupport.domain.service;

import com.voicesupport.domain.model.Citation;
import com.voicesupport.domain.model.ConversationEvent;
import com.voicesupport.domain.model.ConversationResponse;
import com.voicesupport.domain.port.out.ConversationEventStore;
import com.voicesupport.domain.port.out.LlmPort;
import com.voicesupport.domain.port.out.VectorSearchPort;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import java.util.ArrayList;
import java.util.List;

import static org.junit.jupiter.api.Assertions.*;

class ConversationServiceTest {

    private FakeVectorSearchPort vectorSearchPort;
    private FakeLlmPort llmPort;
    private FakeEventStore eventStore;
    private ConversationService service;

    @BeforeEach
    void setUp() {
        vectorSearchPort = new FakeVectorSearchPort();
        llmPort = new FakeLlmPort();
        eventStore = new FakeEventStore();
        service = new ConversationService(vectorSearchPort, llmPort, new EscalationDetector(),
                new GuardrailService(), new QueryReformulator(), eventStore);
    }

    @Test
    void shouldReturnAnswerWithCitations() {
        vectorSearchPort.setCitations(List.of(
                new Citation("telecom-faq.md", "Connexion Internet", "Redémarrez la box", 0.9)
        ));
        llmPort.setAnswer("Essayez de redémarrer votre box.");

        ConversationResponse response = service.ask("conv-1", "Ma box ne marche plus");

        assertEquals("Essayez de redémarrer votre box.", response.answer());
        assertEquals(1, response.citations().size());
        assertEquals("telecom-faq.md", response.citations().get(0).source());
    }

    @Test
    void shouldMaintainConversationHistory() {
        vectorSearchPort.setCitations(List.of(
                new Citation("faq.md", "Section", "Context", 0.8)
        ));
        llmPort.setAnswer("Première réponse");
        service.ask("conv-2", "Question 1");

        llmPort.setAnswer("Deuxième réponse");
        service.ask("conv-2", "Question 2");

        List<String> lastHistory = llmPort.getLastHistory();
        assertTrue(lastHistory.stream().anyMatch(h -> h.contains("Question 1")));
    }

    @Test
    void shouldIsolateConversations() {
        vectorSearchPort.setCitations(List.of(
                new Citation("faq.md", "Section", "Context", 0.8)
        ));
        llmPort.setAnswer("Réponse A");
        service.ask("conv-a", "Question A");

        llmPort.setAnswer("Réponse B");
        service.ask("conv-b", "Question B");

        List<String> historyB = llmPort.getLastHistory();
        assertTrue(historyB.stream().noneMatch(h -> h.contains("Question A")));
    }

    @Test
    void shouldEscalateOnKeyword() {
        vectorSearchPort.setCitations(List.of());
        llmPort.setAnswer("Should not be called");

        ConversationResponse response = service.ask("conv-esc", "Je veux la résiliation de mon abonnement");

        assertTrue(response.answer().contains("conseiller spécialisé"));
        assertTrue(response.citations().isEmpty());
        assertTrue(eventStore.events.stream().anyMatch(ConversationEvent::escalated));
    }

    @Test
    void shouldRecordEventsInStore() {
        vectorSearchPort.setCitations(List.of(
                new Citation("faq.md", "Section", "Context", 0.8)
        ));
        llmPort.setAnswer("Réponse test");

        service.ask("conv-event", "Question test");

        assertEquals(1, eventStore.events.size());
        assertEquals("Question test", eventStore.events.get(0).question());
    }

    static class FakeVectorSearchPort implements VectorSearchPort {
        private List<Citation> citations = List.of();

        void setCitations(List<Citation> citations) { this.citations = citations; }

        @Override
        public List<Citation> searchRelevant(String query, int topK) { return citations; }

        @Override
        public List<Citation> searchRelevant(String query, int topK, String domain) { return citations; }
    }

    static class FakeLlmPort implements LlmPort {
        private String answer = "";
        private List<String> lastHistory = List.of();

        void setAnswer(String answer) { this.answer = answer; }
        List<String> getLastHistory() { return lastHistory; }

        @Override
        public String generateAnswer(String question, List<String> contextChunks, List<String> conversationHistory) {
            this.lastHistory = conversationHistory;
            return answer;
        }

        @Override
        public String generateAnswer(String question, List<String> contextChunks,
                                      List<String> conversationHistory, String systemPrompt) {
            this.lastHistory = conversationHistory;
            return answer;
        }
    }

    static class FakeEventStore implements ConversationEventStore {
        final List<ConversationEvent> events = new ArrayList<>();

        @Override
        public void save(ConversationEvent event) { events.add(event); }

        @Override
        public List<ConversationEvent> findAll() { return events; }

        @Override
        public long countTotal() { return events.size(); }

        @Override
        public long countEscalated() { return events.stream().filter(ConversationEvent::escalated).count(); }

        @Override
        public double averageLatencyMs() { return 0; }
    }
}
