package com.voicesupport.conversation.application.service;

import com.voicesupport.conversation.domain.model.TokenStream;
import com.voicesupport.conversation.domain.model.valueobject.ConversationTurn;
import com.voicesupport.conversation.domain.model.valueobject.GeneratedAnswer;
import com.voicesupport.conversation.domain.model.valueobject.GroundingResult;
import com.voicesupport.conversation.domain.model.valueobject.GuardrailDecision;
import com.voicesupport.conversation.domain.model.valueobject.AnswerLanguage;
import com.voicesupport.conversation.domain.model.valueobject.RetrievedEvidence;
import com.voicesupport.conversation.domain.service.LanguageDetector;
import com.voicesupport.conversation.domain.service.OutputGuardrail;
import com.voicesupport.conversation.fake.FakeGroundQueryUseCase;
import com.voicesupport.conversation.fake.FakeStreamingAnswerGeneratorPort;
import com.voicesupport.conversation.infrastructure.adapter.out.memory.InMemoryConversationMemoryAdapter;
import com.voicesupport.shared.observability.BackendTelemetry;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

import java.util.ArrayList;
import java.util.List;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

@DisplayName("StreamingConversationService (guarded streaming: ground -> stream -> guardrail -> memory)")
class StreamingConversationServiceTest {

    private FakeGroundQueryUseCase grounding;
    private FakeStreamingAnswerGeneratorPort generator;
    private InMemoryConversationMemoryAdapter memory;
    private SimpleMeterRegistry meterRegistry;
    private StreamingConversationService service;
    private final List<String> chunks = new ArrayList<>();

    @BeforeEach
    void setUp() {
        grounding = new FakeGroundQueryUseCase();
        generator = new FakeStreamingAnswerGeneratorPort();
        memory = new InMemoryConversationMemoryAdapter(6, 100);
        meterRegistry = new SimpleMeterRegistry();
        service = new StreamingConversationService(grounding, generator, new OutputGuardrail(), memory,
                new LanguageDetector(AnswerLanguage.ENGLISH), new BackendTelemetry(meterRegistry), 3);
    }

    @Test
    @DisplayName("the configured top-K is forwarded to retrieval grounding (TASK-BE-011)")
    void forwards_configured_top_k() {
        // GIVEN an answerable grounding result
        grounding.setNextResult(GroundingResult.answerable(List.of(
                new RetrievedEvidence("ctx", "s1", "billing", 0.8))));
        generator.setNextTokens(List.of("Réponse. "));

        // WHEN the stream is consumed
        consume("Pourquoi ma facture change ?", "c1");

        // THEN grounding was asked with the configured top-K, not a hardcoded default
        assertEquals(3, grounding.lastTopK);
    }

    @Test
    @DisplayName("blocked grounding emits the canned fallback, never streams the LLM, and is recorded")
    void blocked_grounding_skips_llm() {
        // GIVEN the grounding pipeline blocks the input as off-topic
        grounding.setNextResult(GroundingResult.blocked(GuardrailDecision.offTopic("Hors domaine.")));

        // WHEN the stream is consumed
        GeneratedAnswer answer = consume("Quel temps fait-il ?", "c1");

        // THEN the fallback is the only chunk, the LLM was never called, and memory holds it
        assertEquals(List.of("Hors domaine."), chunks);
        assertEquals(0, generator.callCount);
        assertFalse(answer.grounded());
        assertEquals("Hors domaine.", memory.recentTurns("c1").get(0).assistantText());
    }

    @Test
    @DisplayName("answerable question streams safe sentences, records the voiced answer, forwards evidence")
    void streams_answerable_sentences() {
        // GIVEN strong evidence and a clean two-token stream
        grounding.setNextResult(GroundingResult.answerable(List.of(
                new RetrievedEvidence("La proration explique l'écart.", "s1", "billing", 0.83))));
        generator.setNextTokens(List.of("Votre facture varie. ", "Merci de patienter. "));

        // WHEN the stream is consumed
        GeneratedAnswer answer = consume("Pourquoi ma facture change ?", "c1");

        // THEN sentences are streamed in order, grounded, and the LLM saw the evidence
        assertEquals(List.of("Votre facture varie.", "Merci de patienter."), chunks);
        assertTrue(answer.grounded());
        assertEquals(0.83, answer.confidence());
        assertEquals(1, generator.lastEvidence.size());
        assertEquals("Votre facture varie. Merci de patienter.", memory.recentTurns("c1").get(0).assistantText());
    }

    @Test
    @DisplayName("a mid-stream ungrounded amount stops emission after the safe part and hands off (DEC-002)")
    void ungrounded_amount_stops_stream() {
        // GIVEN evidence without any amount but a stream that invents one
        grounding.setNextResult(GroundingResult.answerable(List.of(
                new RetrievedEvidence("La proration explique l'écart.", "s1", "billing", 0.9))));
        generator.setNextTokens(List.of("Voici le détail. ", "Le montant est 39,99 € ce mois. "));

        // WHEN the stream is consumed
        GeneratedAnswer answer = consume("Combien je paie ?", "c1");

        // THEN only the safe sentence was voiced, followed by a fallback; the amount never appeared
        assertEquals("Voici le détail.", chunks.get(0));
        assertFalse(chunks.contains("Le montant est 39,99 € ce mois."));
        assertFalse(answer.grounded());
        assertTrue(chunks.get(chunks.size() - 1).toLowerCase().contains("conseiller"));
    }

    @Test
    @DisplayName("the second turn is greeted and receives the prior turn as history")
    void second_turn_uses_prior_context() {
        // GIVEN a first completed turn
        grounding.setNextResult(GroundingResult.answerable(List.of(
                new RetrievedEvidence("ctx", "s1", "billing", 0.8))));
        generator.setNextAnswer("La proration explique l'écart. ");
        consume("Pourquoi ma facture change ?", "c1");

        // WHEN a follow-up is asked
        grounding.setNextResult(GroundingResult.answerable(List.of(
                new RetrievedEvidence("ctx", "s1", "billing", 0.8))));
        generator.setNextAnswer("Le mois prochain sera stable. ");
        consume("Et le mois prochain ?", "c1");

        // THEN grounding was told the caller was already greeted and got the prior turn as history
        assertTrue(grounding.lastAlreadyGreeted);
        assertTrue(generator.lastHistory.contains("Client : Pourquoi ma facture change ?"));
    }

    @Test
    @DisplayName("the streamed answer language matches the customer's question language (TASK-BE-015)")
    void streams_in_the_question_language() {
        // GIVEN an answerable grounding result
        grounding.setNextResult(GroundingResult.answerable(List.of(
                new RetrievedEvidence("Prorating explains the difference.", "s1", "billing", 0.8))));
        generator.setNextTokens(List.of("Your bill varies. "));

        // WHEN the customer asks in English
        consume("Why does my bill change this month?", "c1");

        // THEN the streaming LLM is instructed to answer in English
        assertEquals(AnswerLanguage.ENGLISH, generator.lastLanguage);
    }

    @Test
    @DisplayName("a guardrail-fallback stream still records the answer language (no provider) (TASK-BE-015)")
    void fallback_stream_records_answer_language() {
        // GIVEN the grounding pipeline blocks an English off-topic question
        grounding.setNextResult(GroundingResult.blocked(GuardrailDecision.offTopic("Out of scope.")));

        // WHEN the stream is consumed (no LLM call happens)
        consume("What's the weather like today?", "c1");

        // THEN per-turn language observability is still emitted for the fallback, tagged provider=n/a
        double count = meterRegistry.get("voice_support.answer_language")
                .tag("provider", "n/a")
                .tag("language", "en")
                .counter()
                .count();
        assertEquals(1.0, count);
        assertEquals(0, generator.callCount);

        // AND the blocked verdict is counted on the streaming path too (ADR-0034); a mutant dropping
        // the recordGuardrailBlock call in emitFallback would leave no such meter to find.
        double blocks = meterRegistry.get("voice_support.guardrail_block")
                .tag("verdict", "off_topic")
                .counter()
                .count();
        assertEquals(1.0, blocks);
    }

    private GeneratedAnswer consume(String transcript, String conversationId) {
        chunks.clear();
        TokenStream stream = service.converseStream(transcript, conversationId);
        return stream.consume(chunks::add);
    }
}
