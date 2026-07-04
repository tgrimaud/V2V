package com.voicesupport.domain.service;

import com.voicesupport.domain.model.AgentProfile;
import com.voicesupport.domain.model.AgentRegistry;
import com.voicesupport.domain.model.Citation;
import com.voicesupport.domain.model.ConversationEvent;
import com.voicesupport.domain.model.ConversationResponse;
import com.voicesupport.domain.model.ConversationStreamResponse;
import com.voicesupport.domain.model.TokenStream;
import com.voicesupport.domain.port.out.ConversationEventStore;
import com.voicesupport.domain.port.out.LlmPort;
import com.voicesupport.domain.port.out.LlmStreamingPort;
import com.voicesupport.domain.port.out.VectorSearchPort;
import com.voicesupport.infrastructure.adapter.out.persistence.InMemoryConversationStore;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

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
                new QueryReformulator(), intentClassifier, eventStore,
                new InMemoryConversationStore()
        );
    }

    @Test
    void ask_routes_to_support_agent_for_technical_question() {
        // GIVEN
        vectorSearchPort.setCitations(List.of(
                new Citation("telecom-faq.md", "Connexion", "Redémarrez la box", 0.9)
        ));
        llmPort.setAnswer("Essayez de redémarrer votre box.");

        // WHEN
        ConversationResponse response = orchestrator.ask("conv-1", "Ma connexion internet ne marche plus");

        // THEN
        assertEquals("Essayez de redémarrer votre box.", response.answer());
        assertEquals("support", vectorSearchPort.lastDomain);
    }

    @Test
    void ask_routes_to_billing_agent_for_invoice_question() {
        // GIVEN
        vectorSearchPort.setCitations(List.of(
                new Citation("billing-faq.md", "Factures", "Consultez espace client", 0.85)
        ));
        llmPort.setAnswer("Vous pouvez consulter vos factures dans votre espace client.");

        // WHEN
        ConversationResponse response = orchestrator.ask("conv-2", "Comment voir ma facture ?");

        // THEN
        assertEquals("billing", vectorSearchPort.lastDomain);
        assertTrue(response.answer().contains("espace client"));
    }

    @Test
    void ask_routes_to_commercial_agent_for_subscription_question() {
        // GIVEN
        vectorSearchPort.setCitations(List.of(
                new Citation("commercial-faq.md", "Souscription", "Rendez-vous sur notre site", 0.87)
        ));
        llmPort.setAnswer("Rendez-vous sur notre site pour souscrire.");

        // WHEN
        ConversationResponse response = orchestrator.ask("conv-3", "Je voudrais souscrire à la fibre");

        // THEN
        assertEquals("commercial", vectorSearchPort.lastDomain);
        assertTrue(response.answer().contains("souscrire"));
    }

    @Test
    void ask_keeps_same_agent_across_turns_of_a_session() {
        // GIVEN
        vectorSearchPort.setCitations(List.of(
                new Citation("billing-faq.md", "Factures", "Info facture", 0.8)
        ));
        llmPort.setAnswer("Réponse facturation");

        // WHEN
        orchestrator.ask("conv-sticky", "J'ai un problème avec mon prélèvement");
        llmPort.setAnswer("Suite facturation");
        orchestrator.ask("conv-sticky", "Ok et quand sera la prochaine ?");

        // THEN
        assertEquals("billing", orchestrator.getCurrentAgentId("conv-sticky"));
    }

    @Test
    void ask_switches_agent_when_intent_changes() {
        // GIVEN
        vectorSearchPort.setCitations(List.of(
                new Citation("faq.md", "Section", "Context", 0.8)
        ));
        llmPort.setAnswer("Réponse support");
        orchestrator.ask("conv-switch", "Ma box ne se connecte plus à internet");

        // WHEN
        llmPort.setAnswer("Réponse facturation");
        orchestrator.ask("conv-switch", "En fait je voudrais consulter ma facture et mon prélèvement");

        // THEN
        assertEquals("billing", orchestrator.getCurrentAgentId("conv-switch"));
    }

    @Test
    void ask_escalates_regardless_of_current_agent() {
        // GIVEN / WHEN
        ConversationResponse response = orchestrator.ask("conv-esc", "Je veux la résiliation de mon abonnement");

        // THEN
        assertTrue(response.answer().contains("conseiller spécialisé"));
    }

    @Test
    void ask_blocks_off_topic_question_with_guardrail() {
        // GIVEN / WHEN
        ConversationResponse response = orchestrator.ask("conv-guard", "Quel est la météo de demain ?");

        // THEN
        assertTrue(response.answer().contains("sort de mon domaine") ||
                response.answer().contains("outside my area"));
    }

    @Test
    void ask_includes_seeded_greeting_in_history_of_first_user_turn() {
        // GIVEN
        orchestrator.seedAssistantMessage("conv-seed",
                "Bonjour ! Je suis votre assistant virtuel du support télécom.");
        vectorSearchPort.setCitations(List.of(
                new Citation("billing-faq.md", "Factures", "Info facture", 0.9)
        ));
        llmPort.setAnswer("Je vois que vous avez un problème de facture.");

        // WHEN
        orchestrator.ask("conv-seed", "Bonjour, j'ai un problème de facture.");

        // THEN
        List<String> history = llmPort.getLastHistory();
        assertEquals(1, history.size());
        assertTrue(history.get(0).contains("assistant virtuel"),
                "The first user turn should see the seeded greeting in history so the LLM does not greet again");
    }

    @Test
    void ask_does_not_re_greet_when_user_greets_after_seeded_welcome() {
        // GIVEN
        orchestrator.seedAssistantMessage("conv-regreet",
                "Bonjour ! Je suis votre assistant virtuel du support télécom.");

        // WHEN
        ConversationResponse response = orchestrator.ask("conv-regreet", "Bonjour");

        // THEN
        assertEquals("Je vous écoute, que puis-je faire pour vous ?", response.answer());
    }

    @Test
    void ask_greets_with_bonjour_on_first_user_greeting_without_seeded_welcome() {
        // GIVEN / WHEN
        ConversationResponse response = orchestrator.ask("conv-firstgreet", "Bonjour");

        // THEN
        assertEquals("Bonjour ! Comment puis-je vous aider ?", response.answer());
    }

    @Test
    void ask_ignores_blank_seed_message() {
        // GIVEN
        orchestrator.seedAssistantMessage("conv-blank", "   ");
        vectorSearchPort.setCitations(List.of(
                new Citation("billing-faq.md", "Factures", "Info facture", 0.9)
        ));
        llmPort.setAnswer("Réponse");

        // WHEN
        orchestrator.ask("conv-blank", "Comment voir ma facture ?");

        // THEN
        assertTrue(llmPort.getLastHistory().isEmpty());
    }

    @Test
    void ask_stream_returns_tokens_with_agent_routing() {
        // GIVEN
        vectorSearchPort.setCitations(List.of(
                new Citation("billing-faq.md", "Paiement", "RIB info", 0.9)
        ));
        llmPort.setStreamTokens(List.of("Vous ", "pouvez ", "changer ", "votre RIB."));

        // WHEN
        ConversationStreamResponse result =
                orchestrator.askStream("conv-stream", "Comment changer mon RIB ?");

        // THEN
        assertFalse(result.escalated());
        assertFalse(result.guardrailBlocked());
        assertEquals("billing", result.agentId());
        StringBuilder fullAnswer = new StringBuilder();
        result.tokens().forEach(fullAnswer::append);
        assertTrue(fullAnswer.toString().contains("RIB"));
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
        public TokenStream streamAnswer(String question, List<String> contextChunks, List<String> conversationHistory) {
            return streamAnswer(question, contextChunks, conversationHistory, null);
        }

        @Override
        public TokenStream streamAnswer(String question, List<String> contextChunks,
                                        List<String> conversationHistory, String systemPrompt) {
            this.lastHistory = conversationHistory;
            return TokenStream.fromIterable(streamTokens);
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
