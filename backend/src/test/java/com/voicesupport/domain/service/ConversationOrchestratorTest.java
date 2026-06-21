package com.voicesupport.domain.service;

import com.voicesupport.domain.model.AgentProfile;
import com.voicesupport.domain.model.AgentRegistry;
import com.voicesupport.domain.model.Citation;
import com.voicesupport.domain.model.ConversationEvent;
import com.voicesupport.domain.model.ConversationResponse;
import com.voicesupport.domain.port.out.ConversationEventStore;
import com.voicesupport.domain.port.out.LlmPort;
import com.voicesupport.domain.port.out.LlmStreamingPort;
import com.voicesupport.domain.port.out.VectorSearchPort;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import reactor.core.publisher.Flux;

import java.util.ArrayList;
import java.util.List;

import static org.junit.jupiter.api.Assertions.*;

class ConversationOrchestratorTest {

    private FakeVectorSearchPort vectorSearchPort;
    private FakeLlmPort llmPort;
    private FakeEventStore eventStore;
    private ConversationOrchestrator orchestrator;

    @BeforeEach
    void setUp() {
        vectorSearchPort = new FakeVectorSearchPort();
        llmPort = new FakeLlmPort();
        eventStore = new FakeEventStore();
        AgentRegistry registry = new AgentRegistry(
                List.of(AgentProfile.support(), AgentProfile.billing(), AgentProfile.commercial()),
                "support"
        );
        IntentClassifier intentClassifier = new IntentClassifier(registry);

        orchestrator = new ConversationOrchestrator(
                vectorSearchPort, llmPort, llmPort,
                new EscalationDetector(), new GuardrailService(),
                new QueryReformulator(), intentClassifier, eventStore
        );
    }

    @Test
    void shouldRouteToSupportAgentForTechnicalQuestion() {
        vectorSearchPort.setCitations(List.of(
                new Citation("telecom-faq.md", "Connexion", "Redémarrez la box", 0.9)
        ));
        llmPort.setAnswer("Essayez de redémarrer votre box.");

        ConversationResponse response = orchestrator.ask("conv-1", "Ma connexion internet ne marche plus");

        assertEquals("Essayez de redémarrer votre box.", response.answer());
        assertEquals("support", vectorSearchPort.lastDomain);
    }

    @Test
    void shouldRouteToBillingAgentForInvoiceQuestion() {
        vectorSearchPort.setCitations(List.of(
                new Citation("billing-faq.md", "Factures", "Consultez espace client", 0.85)
        ));
        llmPort.setAnswer("Vous pouvez consulter vos factures dans votre espace client.");

        ConversationResponse response = orchestrator.ask("conv-2", "Comment voir ma facture ?");

        assertEquals("billing", vectorSearchPort.lastDomain);
        assertTrue(response.answer().contains("espace client"));
    }

    @Test
    void shouldRouteToCommercialAgentForSubscriptionQuestion() {
        vectorSearchPort.setCitations(List.of(
                new Citation("commercial-faq.md", "Souscription", "Rendez-vous sur notre site", 0.87)
        ));
        llmPort.setAnswer("Rendez-vous sur notre site pour souscrire.");

        ConversationResponse response = orchestrator.ask("conv-3", "Je voudrais souscrire à la fibre");

        assertEquals("commercial", vectorSearchPort.lastDomain);
        assertTrue(response.answer().contains("souscrire"));
    }

    @Test
    void shouldMaintainAgentStickinessInSession() {
        vectorSearchPort.setCitations(List.of(
                new Citation("billing-faq.md", "Factures", "Info facture", 0.8)
        ));
        llmPort.setAnswer("Réponse facturation");

        orchestrator.ask("conv-sticky", "J'ai un problème avec mon prélèvement");
        assertEquals("billing", orchestrator.getCurrentAgentId("conv-sticky"));

        llmPort.setAnswer("Suite facturation");
        orchestrator.ask("conv-sticky", "Ok et quand sera la prochaine ?");
        assertEquals("billing", orchestrator.getCurrentAgentId("conv-sticky"));
    }

    @Test
    void shouldSwitchAgentWhenIntentChanges() {
        vectorSearchPort.setCitations(List.of(
                new Citation("faq.md", "Section", "Context", 0.8)
        ));
        llmPort.setAnswer("Réponse support");
        orchestrator.ask("conv-switch", "Ma box ne se connecte plus à internet");
        assertEquals("support", orchestrator.getCurrentAgentId("conv-switch"));

        llmPort.setAnswer("Réponse facturation");
        orchestrator.ask("conv-switch", "En fait je voudrais consulter ma facture et mon prélèvement");
        assertEquals("billing", orchestrator.getCurrentAgentId("conv-switch"));
    }

    @Test
    void shouldHandleEscalationRegardlessOfAgent() {
        ConversationResponse response = orchestrator.ask("conv-esc", "Je veux la résiliation de mon abonnement");
        assertTrue(response.answer().contains("conseiller spécialisé"));
    }

    @Test
    void shouldHandleGuardrailBlock() {
        ConversationResponse response = orchestrator.ask("conv-guard", "Quel est la météo de demain ?");
        assertTrue(response.answer().contains("sort de mon domaine") ||
                response.answer().contains("outside my area"));
    }

    @Test
    void shouldStreamWithAgentRouting() {
        vectorSearchPort.setCitations(List.of(
                new Citation("billing-faq.md", "Paiement", "RIB info", 0.9)
        ));
        llmPort.setStreamTokens(List.of("Vous ", "pouvez ", "changer ", "votre RIB."));

        ConversationOrchestrator.StreamingResult result =
                orchestrator.askStream("conv-stream", "Comment changer mon RIB ?");

        assertFalse(result.escalated());
        assertFalse(result.guardrailBlocked());
        assertEquals("billing", result.agentId());

        String fullAnswer = String.join("", result.tokens().collectList().block());
        assertTrue(fullAnswer.contains("RIB"));
    }

    static class FakeVectorSearchPort implements VectorSearchPort {
        private List<Citation> citations = List.of();
        String lastDomain;

        void setCitations(List<Citation> citations) { this.citations = citations; }

        @Override
        public List<Citation> searchRelevant(String query, int topK) {
            return searchRelevant(query, topK, null);
        }

        @Override
        public List<Citation> searchRelevant(String query, int topK, String domain) {
            this.lastDomain = domain;
            return citations;
        }
    }

    static class FakeLlmPort implements LlmPort, LlmStreamingPort {
        private String answer = "";
        private List<String> streamTokens = List.of();
        private List<String> lastHistory = List.of();

        void setAnswer(String answer) { this.answer = answer; }
        void setStreamTokens(List<String> tokens) { this.streamTokens = tokens; }
        List<String> getLastHistory() { return lastHistory; }

        @Override
        public String generateAnswer(String question, List<String> contextChunks, List<String> conversationHistory) {
            return generateAnswer(question, contextChunks, conversationHistory, null);
        }

        @Override
        public String generateAnswer(String question, List<String> contextChunks,
                                      List<String> conversationHistory, String systemPrompt) {
            this.lastHistory = conversationHistory;
            return answer;
        }

        @Override
        public Flux<String> streamAnswer(String question, List<String> contextChunks, List<String> conversationHistory) {
            return streamAnswer(question, contextChunks, conversationHistory, null);
        }

        @Override
        public Flux<String> streamAnswer(String question, List<String> contextChunks,
                                          List<String> conversationHistory, String systemPrompt) {
            this.lastHistory = conversationHistory;
            return Flux.fromIterable(streamTokens);
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
