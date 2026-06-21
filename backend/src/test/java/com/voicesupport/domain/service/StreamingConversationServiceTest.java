package com.voicesupport.domain.service;

import com.voicesupport.domain.model.Citation;
import com.voicesupport.domain.model.ConversationEvent;
import com.voicesupport.domain.port.out.ConversationEventStore;
import com.voicesupport.domain.port.out.LlmStreamingPort;
import com.voicesupport.domain.port.out.VectorSearchPort;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import reactor.core.publisher.Flux;

import java.util.ArrayList;
import java.util.List;

import static org.junit.jupiter.api.Assertions.*;

class StreamingConversationServiceTest {

    private FakeVectorSearchPort vectorSearchPort;
    private FakeLlmStreamingPort llmStreamingPort;
    private FakeEventStore eventStore;
    private StreamingConversationService service;

    @BeforeEach
    void setUp() {
        vectorSearchPort = new FakeVectorSearchPort();
        llmStreamingPort = new FakeLlmStreamingPort();
        eventStore = new FakeEventStore();
        service = new StreamingConversationService(
                vectorSearchPort, llmStreamingPort, new EscalationDetector(),
                new GuardrailService(), new QueryReformulator(), eventStore);
    }

    @Test
    void shouldStreamTokensFromLlm() {
        // GIVEN
        vectorSearchPort.setCitations(List.of(
                new Citation("faq.md", "Section", "Redémarrez la box", 0.9)
        ));
        llmStreamingPort.setTokens(List.of("Bonjour", ", ", "essayez ", "de ", "redémarrer."));

        // WHEN
        StreamingConversationService.StreamingResult result =
                service.askStream("conv-1", "Ma box ne marche plus");

        // THEN
        assertFalse(result.escalated());
        assertEquals(1, result.citations().size());

        List<String> collected = result.tokens().collectList().block();
        assertNotNull(collected);
        assertEquals(5, collected.size());
        assertEquals("Bonjour", collected.get(0));
        assertEquals("de ", collected.get(3));
    }

    @Test
    void shouldReturnEscalationWithoutStreamingLlm() {
        // GIVEN
        vectorSearchPort.setCitations(List.of());
        llmStreamingPort.setTokens(List.of("Should not be called"));

        // WHEN
        StreamingConversationService.StreamingResult result =
                service.askStream("conv-esc", "Je veux la résiliation");

        // THEN
        assertTrue(result.escalated());
        assertTrue(result.citations().isEmpty());

        String text = result.tokens().blockFirst();
        assertNotNull(text);
        assertTrue(text.contains("conseiller spécialisé"));
        assertEquals(1, eventStore.events.size());
        assertTrue(eventStore.events.get(0).escalated());
    }

    @Test
    void shouldRecordCompletionEvent() {
        // GIVEN
        vectorSearchPort.setCitations(List.of(
                new Citation("source.md", "S1", "Context chunk", 0.8)
        ));
        llmStreamingPort.setTokens(List.of("Token1", " Token2"));

        // WHEN
        service.askStream("conv-rec", "Question");
        service.recordCompletion("conv-rec", "Question", "Token1 Token2",
                List.of(new Citation("source.md", "S1", "Context chunk", 0.8)),
                System.currentTimeMillis() - 500);

        // THEN
        assertEquals(1, eventStore.events.size());
        assertEquals("Token1 Token2", eventStore.events.get(0).answer());
        assertFalse(eventStore.events.get(0).escalated());
    }

    @Test
    void shouldIsolateStreamingSessions() {
        // GIVEN
        vectorSearchPort.setCitations(List.of(
                new Citation("faq.md", "Section", "Context", 0.8)
        ));
        llmStreamingPort.setTokens(List.of("Answer A"));
        service.askStream("conv-a", "Question A");
        service.recordCompletion("conv-a", "Question A", "Answer A", List.of(), System.currentTimeMillis());

        llmStreamingPort.setTokens(List.of("Answer B"));

        // WHEN
        service.askStream("conv-b", "Question B");

        // THEN — conv-b history should not contain conv-a content
        List<String> lastHistory = llmStreamingPort.getLastHistory();
        assertTrue(lastHistory.stream().noneMatch(h -> h.contains("Question A")));
    }

    static class FakeVectorSearchPort implements VectorSearchPort {
        private List<Citation> citations = List.of();

        void setCitations(List<Citation> citations) { this.citations = citations; }

        @Override
        public List<Citation> searchRelevant(String query, int topK) { return citations; }

        @Override
        public List<Citation> searchRelevant(String query, int topK, String domain) { return citations; }
    }

    static class FakeLlmStreamingPort implements LlmStreamingPort {
        private List<String> tokens = List.of();
        private List<String> lastHistory = List.of();

        void setTokens(List<String> tokens) { this.tokens = tokens; }
        List<String> getLastHistory() { return lastHistory; }

        @Override
        public Flux<String> streamAnswer(String question, List<String> contextChunks, List<String> conversationHistory) {
            return streamAnswer(question, contextChunks, conversationHistory, null);
        }

        @Override
        public Flux<String> streamAnswer(String question, List<String> contextChunks,
                                          List<String> conversationHistory, String systemPrompt) {
            this.lastHistory = conversationHistory;
            return Flux.fromIterable(tokens);
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
