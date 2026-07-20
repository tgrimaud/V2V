package com.voicesupport.conversation.domain.service;

import com.voicesupport.conversation.domain.model.valueobject.GeneratedAnswer;
import com.voicesupport.conversation.domain.model.valueobject.RetrievedEvidence;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

import java.util.ArrayList;
import java.util.List;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

@DisplayName("GuardedSentenceEmitter (per-sentence output guardrail before emission, DEC-002)")
class GuardedSentenceEmitterTest {

    private final OutputGuardrail guardrail = new OutputGuardrail();
    private final List<String> emitted = new ArrayList<>();

    @Test
    @DisplayName("emits each safe sentence in order and returns a grounded answer with confidence")
    void streamsSafeSentences() {
        // GIVEN evidence with no amount and an emitter
        GuardedSentenceEmitter emitter = emitterFor(List.of(
                new RetrievedEvidence("La proration explique l'écart.", "s1", "billing", 0.83)));

        // WHEN a two-sentence answer is streamed
        emitter.accept("Votre facture varie à cause de la proration. Merci de patienter.");
        GeneratedAnswer answer = emitter.finish();

        // THEN both sentences were emitted and the result is grounded with the given confidence
        assertEquals(List.of(
                "Votre facture varie à cause de la proration.", "Merci de patienter."), emitted);
        assertTrue(answer.grounded());
        assertEquals(0.83, answer.confidence());
        assertEquals("Votre facture varie à cause de la proration. Merci de patienter.", answer.text());
    }

    @Test
    @DisplayName("never emits a sentence carrying an ungrounded amount; hands off instead (DEC-002)")
    void blocksUngroundedAmount() {
        // GIVEN evidence without any amount
        GuardedSentenceEmitter emitter = emitterFor(List.of(
                new RetrievedEvidence("La proration explique l'écart.", "s1", "billing", 0.9)));

        // WHEN a later sentence invents an amount
        emitter.accept("Voici le détail. Le montant est 39,99 € ce mois.");
        GeneratedAnswer answer = emitter.finish();

        // THEN the safe sentence was voiced but the invented amount never was; a fallback closes it
        assertEquals("Voici le détail.", emitted.get(0));
        assertFalse(emitted.contains("Le montant est 39,99 € ce mois."));
        assertFalse(answer.grounded());
        assertNull(answer.confidence());
        assertTrue(lastEmitted().toLowerCase().contains("conseiller"));
    }

    @Test
    @DisplayName("lets a grounded amount through when it is backed by the evidence")
    void allowsGroundedAmount() {
        // GIVEN evidence that carries the amount
        GuardedSentenceEmitter emitter = emitterFor(List.of(
                new RetrievedEvidence("Votre forfait est à 39,99 € par mois.", "s1", "billing", 0.95)));

        // WHEN the answer voices that same amount
        emitter.accept("Votre forfait est de 39,99 € par mois. ");
        GeneratedAnswer answer = emitter.finish();

        // THEN it is emitted and the answer stays grounded
        assertEquals(List.of("Votre forfait est de 39,99 € par mois."), emitted);
        assertTrue(answer.grounded());
    }

    @Test
    @DisplayName("an empty stream becomes a safe low-confidence fallback")
    void emptyStreamFallsBack() {
        // GIVEN an emitter that receives no tokens
        GuardedSentenceEmitter emitter = emitterFor(List.of(
                new RetrievedEvidence("ctx", "s1", "billing", 0.7)));

        // WHEN finishing without any token
        GeneratedAnswer answer = emitter.finish();

        // THEN a single safe hand-off is emitted, not a grounded answer
        assertEquals(1, emitted.size());
        assertFalse(answer.grounded());
        assertTrue(lastEmitted().toLowerCase().contains("conseiller"));
    }

    @Test
    @DisplayName("an explicit refusal sentence is not voiced; the canned hand-off is emitted instead")
    void refusalBecomesFallback() {
        // GIVEN normal evidence
        GuardedSentenceEmitter emitter = emitterFor(List.of(
                new RetrievedEvidence("Contenu de support.", "s1", "support", 0.9)));

        // WHEN the model emits the refusal sentence
        emitter.accept("Je n'ai pas cette information, je vous transfère à un conseiller. ");
        GeneratedAnswer answer = emitter.finish();

        // THEN the raw refusal is not voiced verbatim; a safe fallback is returned
        assertFalse(answer.grounded());
        assertTrue(lastEmitted().toLowerCase().contains("conseiller"));
    }

    private GuardedSentenceEmitter emitterFor(List<RetrievedEvidence> evidence) {
        return new GuardedSentenceEmitter("Question ?", evidence, guardrail, emitted::add, 0.83);
    }

    private String lastEmitted() {
        return emitted.get(emitted.size() - 1);
    }
}
