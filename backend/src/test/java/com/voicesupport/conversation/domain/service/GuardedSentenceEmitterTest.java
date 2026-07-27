package com.voicesupport.conversation.domain.service;

import com.voicesupport.conversation.domain.model.valueobject.AnswerLanguage;
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
    void streams_safe_sentences() {
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
    void blocks_ungrounded_amount() {
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
    @DisplayName("emits every safe sentence completed within a single token (loop does not stop early)")
    void emits_all_sentences_from_one_token() {
        // GIVEN evidence with no amount
        GuardedSentenceEmitter emitter = emitterFor(List.of(
                new RetrievedEvidence("Contexte.", "s1", "billing", 0.9)));

        // WHEN a single token completes TWO sentences at once (both terminated + trailing space)
        emitter.accept("Un. Deux. ");

        // THEN both are emitted in the same accept() call; a mutant that returns after the first
        // safe sentence (negated not-blocked guard inside the loop) would drop "Deux."
        assertEquals(List.of("Un.", "Deux."), emitted);
    }

    @Test
    @DisplayName("lets a grounded amount through when it is backed by the evidence")
    void allows_grounded_amount() {
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
    void empty_stream_falls_back() {
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
    void refusal_becomes_fallback() {
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
        // The turn language is decided once upstream; here French, so the hand-off wording is French
        // (contains "conseiller"). The emitter no longer re-detects language from the answer text,
        // it uses the decided language passed in (BUG-002 / TASK-BE-015).
        return new GuardedSentenceEmitter(evidence, guardrail, emitted::add, 0.83, AnswerLanguage.FRENCH);
    }

    private String lastEmitted() {
        return emitted.get(emitted.size() - 1);
    }
}
