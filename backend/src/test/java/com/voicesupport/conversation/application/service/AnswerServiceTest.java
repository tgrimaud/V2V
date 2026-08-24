package com.voicesupport.conversation.application.service;

import com.voicesupport.conversation.domain.model.valueobject.AnswerLanguage;
import com.voicesupport.conversation.domain.model.valueobject.GeneratedAnswer;
import com.voicesupport.conversation.domain.model.valueobject.GroundingResult;
import com.voicesupport.conversation.domain.model.valueobject.GuardrailDecision;
import com.voicesupport.conversation.domain.model.valueobject.RetrievedEvidence;
import com.voicesupport.conversation.domain.service.LanguageDetector;
import com.voicesupport.conversation.domain.service.OutputGuardrail;
import com.voicesupport.conversation.fake.FakeAnswerGeneratorPort;
import com.voicesupport.conversation.fake.FakeGroundQueryUseCase;
import com.voicesupport.shared.observability.BackendTelemetry;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

import java.util.List;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

@DisplayName("AnswerService (ground -> LLM wording -> output guardrail)")
class AnswerServiceTest {

    private FakeGroundQueryUseCase grounding;
    private FakeAnswerGeneratorPort generator;
    private SimpleMeterRegistry meterRegistry;
    private AnswerService service;

    @BeforeEach
    void setUp() {
        grounding = new FakeGroundQueryUseCase();
        generator = new FakeAnswerGeneratorPort();
        meterRegistry = new SimpleMeterRegistry();
        service = new AnswerService(
                grounding, generator, new OutputGuardrail(),
                new LanguageDetector(AnswerLanguage.ENGLISH), new BackendTelemetry(meterRegistry));
    }

    @Test
    @DisplayName("blocked grounding returns the canned fallback and never calls the LLM")
    void blocked_grounding_skips_llm() {
        // GIVEN the grounding pipeline blocks the input as off-topic
        grounding.setNextResult(GroundingResult.blocked(GuardrailDecision.offTopic("Hors domaine.")));

        // WHEN answering
        GeneratedAnswer answer = service.answer("Quel temps fait-il ?", "billing", 4, true, List.of());

        // THEN the fallback is returned, not grounded, and the LLM was never invoked
        assertFalse(answer.grounded());
        assertNull(answer.confidence());
        assertEquals("Hors domaine.", answer.text());
        assertEquals(0, generator.callCount);
    }

    @Test
    @DisplayName("answerable question is worded by the LLM with retrieval best-score as confidence")
    void answerable_produces_grounded_answer() {
        // GIVEN strong evidence and a clean LLM answer
        grounding.setNextResult(GroundingResult.answerable(List.of(
                new RetrievedEvidence("La proration explique l'écart.", "billing-faq#1", "billing", 0.83),
                new RetrievedEvidence("Un changement d'offre est facturé au prorata.", "billing-faq#2", "billing", 0.71))));
        generator.setNextAnswer("Votre facture varie à cause de la proration lors d'un changement d'offre.");

        // WHEN answering
        GeneratedAnswer answer = service.answer("Pourquoi ma facture change ?", "billing", 4, true, List.of());

        // THEN it is grounded, confidence is the best evidence score, LLM saw the evidence
        assertTrue(answer.grounded());
        assertEquals(0.83, answer.confidence());
        assertEquals(1, generator.callCount);
        assertEquals(2, generator.lastEvidence.size());
        assertTrue(generator.lastHistory.isEmpty());
    }

    @Test
    @DisplayName("an ungrounded amount in the LLM answer is replaced by a safe hand-off (DEC-002)")
    void fabricated_amount_replaced_by_fallback() {
        // GIVEN strong evidence with no amount but the LLM invents one
        grounding.setNextResult(GroundingResult.answerable(List.of(
                new RetrievedEvidence("La proration explique l'écart.", "billing-faq#1", "billing", 0.9))));
        generator.setNextAnswer("Votre facture est de 39,99 € ce mois-ci.");

        // WHEN answering
        GeneratedAnswer answer = service.answer("Combien je paie ?", "billing", 4, true, List.of());

        // THEN the invented amount is not voiced; a safe fallback is returned instead
        assertFalse(answer.grounded());
        assertNull(answer.confidence());
        assertTrue(answer.text().toLowerCase().contains("conseiller"));

        // AND the DEC-002 output block is counted so QA/Ops can observe suppression of a fabricated
        // amount; a mutant that drops the recordGuardrailBlock call on the output path leaves no meter.
        double blocks = meterRegistry.get("voice_support.guardrail_block")
                .tag("verdict", "ungrounded")
                .counter()
                .count();
        assertEquals(1.0, blocks);
    }

    @Test
    @DisplayName("an empty LLM answer becomes a safe fallback, never a grounded answer")
    void empty_answer_becomes_fallback() {
        // GIVEN strong evidence but the LLM returns nothing
        grounding.setNextResult(GroundingResult.answerable(List.of(
                new RetrievedEvidence("La proration explique l'écart.", "billing-faq#1", "billing", 0.88))));
        generator.setNextAnswer("   ");

        // WHEN answering
        GeneratedAnswer answer = service.answer("Pourquoi ma facture change ?", "billing", 4, true, List.of());

        // THEN a safe hand-off is returned without a misleading confidence signal
        assertFalse(answer.grounded());
        assertNull(answer.confidence());
        assertTrue(answer.text().toLowerCase().contains("conseiller"));
    }

    @Test
    @DisplayName("an explicit LLM refusal is reported as a fallback, not grounded")
    void refusal_answer_becomes_fallback() {
        // GIVEN strong evidence but the LLM emits the canned transfer sentence
        grounding.setNextResult(GroundingResult.answerable(List.of(
                new RetrievedEvidence("Contenu de support.", "support-faq#1", "support", 0.9))));
        generator.setNextAnswer("Je n'ai pas cette information, je vous transfère à un conseiller.");

        // WHEN answering
        GeneratedAnswer answer = service.answer("Question obscure ?", "support", 4, true, List.of());

        // THEN it is a non-grounded fallback
        assertFalse(answer.grounded());
        assertNull(answer.confidence());
    }

    @Test
    @DisplayName("grounding parameters are forwarded unchanged")
    void forwards_parameters() {
        // GIVEN an answerable result
        grounding.setNextResult(GroundingResult.answerable(List.of(
                new RetrievedEvidence("ctx", "s1", "support", 0.7))));

        // WHEN answering with explicit parameters
        service.answer("Comment configurer ma box ?", "support", 6, true, List.of());

        // THEN the grounding pipeline received them verbatim
        assertEquals("Comment configurer ma box ?", grounding.lastQuestion);
        assertEquals("support", grounding.lastDomain);
        assertEquals(6, grounding.lastTopK);
        assertTrue(grounding.lastAlreadyGreeted);
    }

    @Test
    @DisplayName("the answer language matches the customer's question language (TASK-BE-015)")
    void answers_in_the_question_language() {
        // GIVEN an answerable result
        grounding.setNextResult(GroundingResult.answerable(List.of(
                new RetrievedEvidence("Prorating explains the difference.", "billing-faq#1", "billing", 0.8))));

        // WHEN the customer asks in English
        service.answer("Why does my bill change this month?", "billing", 4, true, List.of());

        // THEN the LLM is instructed to answer in English
        assertEquals(AnswerLanguage.ENGLISH, generator.lastLanguage);

        // WHEN the customer asks in French
        service.answer("Pourquoi ma facture change ce mois-ci ?", "billing", 4, true, List.of());

        // THEN the LLM is instructed to answer in French
        assertEquals(AnswerLanguage.FRENCH, generator.lastLanguage);
    }

    @Test
    @DisplayName("a guardrail-fallback turn still records the answer language (no provider) (TASK-BE-015)")
    void fallback_turn_records_answer_language() {
        // GIVEN the grounding pipeline blocks an English off-topic question
        grounding.setNextResult(GroundingResult.blocked(GuardrailDecision.offTopic("Out of scope.")));

        // WHEN answering (no LLM call happens)
        service.answer("What's the weather like today?", "billing", 4, true, List.of());

        // THEN per-turn language observability is still emitted for the fallback, tagged provider=n/a
        double count = meterRegistry.get("voice_support.answer_language")
                .tag("provider", "n/a")
                .tag("language", "en")
                .counter()
                .count();
        assertEquals(1.0, count);
        assertEquals(0, generator.callCount);

        // AND the blocked verdict is counted so clarify/low-confidence/off-topic rates are observable
        // (ADR-0034); a mutant that drops the recordGuardrailBlock call leaves no such meter to find.
        double blocks = meterRegistry.get("voice_support.guardrail_block")
                .tag("verdict", "off_topic")
                .counter()
                .count();
        assertEquals(1.0, blocks);
    }

    @Test
    @DisplayName("the prior conversation history is forwarded to the LLM unchanged (TASK-BE-006)")
    void forwards_history_to_llm() {
        // GIVEN an answerable result and a non-empty prior history
        grounding.setNextResult(GroundingResult.answerable(List.of(
                new RetrievedEvidence("La proration explique l'écart.", "billing-faq#1", "billing", 0.8))));
        List<String> history = List.of(
                "Client : Pourquoi ma facture change ?", "Assistant : À cause de la proration.");

        // WHEN answering with that history
        service.answer("Et le mois prochain ?", "billing", 4, true, history);

        // THEN the LLM receives the real history verbatim; a mutant that swaps the null-guard branch
        // (returning an empty list for a non-null history) would forward nothing.
        assertEquals(history, generator.lastHistory);
    }
}
