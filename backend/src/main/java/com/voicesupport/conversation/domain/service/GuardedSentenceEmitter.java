package com.voicesupport.conversation.domain.service;

import com.voicesupport.conversation.domain.model.valueobject.AnswerLanguage;
import com.voicesupport.conversation.domain.model.valueobject.GeneratedAnswer;
import com.voicesupport.conversation.domain.model.valueobject.GuardrailDecision;
import com.voicesupport.conversation.domain.model.valueobject.RetrievedEvidence;

import java.util.List;
import java.util.function.Consumer;

// Guarded, sentence-level SSE emission (ADR-0013 / DEC-002). Buffers streamed tokens into
// sentences and lets the OutputGuardrail vet each one BEFORE it is emitted, so an ungrounded
// currency amount (or a refusal/non-answer) is never voiced. On a blocked sentence the stream
// stops consuming further tokens and emits the safe hand-off message as the terminal chunk,
// preserving DEC-002 on the streamed path exactly like the synchronous AnswerService does.
public class GuardedSentenceEmitter {

    private final List<RetrievedEvidence> evidence;
    private final OutputGuardrail outputGuardrail;
    private final Consumer<String> onChunk;
    private final double groundedConfidence;
    private final AnswerLanguage language;
    private final SentenceSegmenter segmenter = new SentenceSegmenter();
    private final StringBuilder voiced = new StringBuilder();
    private boolean blocked;
    // BUG-024: set when a hand-off/low-confidence sentence arrives AFTER grounded content was
    // already voiced (a trailing courtesy transfer, not a refusal). It stops consuming further
    // tokens like `blocked`, but keeps the already-voiced answer grounded (no fallback emitted).
    private boolean truncatedAfterGrounded;
    private String fallbackMessage;
    // Verdict of the block that produced a fallback (DEC-002 output block, or LOW_CONFIDENCE when
    // nothing was voiced). Null on a grounded answer. The application service reads it to emit the
    // guardrail-block telemetry without pulling observability infrastructure into the domain.
    private GuardrailDecision.Verdict blockedVerdict;

    public GuardedSentenceEmitter(
            List<RetrievedEvidence> evidence,
            OutputGuardrail outputGuardrail,
            Consumer<String> onChunk,
            double groundedConfidence,
            AnswerLanguage language) {
        this.evidence = evidence;
        this.outputGuardrail = outputGuardrail;
        this.onChunk = onChunk;
        this.groundedConfidence = groundedConfidence;
        this.language = language;
    }

    public void accept(String token) {
        if (stopped()) {
            return;
        }
        for (String sentence : segmenter.feed(token)) {
            emit(sentence);
            if (stopped()) {
                return;
            }
        }
    }

    public GeneratedAnswer finish() {
        for (String sentence : segmenter.flush()) {
            emit(sentence);
        }
        if (blocked) {
            onChunk.accept(fallbackMessage);
            return GeneratedAnswer.fallback(fallbackMessage, blockedVerdict);
        }
        if (voiced.isEmpty()) {
            blockedVerdict = GuardrailDecision.Verdict.LOW_CONFIDENCE;
            String message = GuardrailMessages.lowConfidence(language);
            onChunk.accept(message);
            return GeneratedAnswer.fallback(message, blockedVerdict);
        }
        return GeneratedAnswer.grounded(voiced.toString(), groundedConfidence);
    }

    private void emit(String sentence) {
        if (stopped()) {
            return;
        }
        GuardrailDecision decision = outputGuardrail.check(sentence, evidence, language);
        if (decision.blocked()) {
            // BUG-024: a LOW_CONFIDENCE (hand-off / non-answer) sentence AFTER grounded content was
            // already voiced is a trailing courtesy transfer, not a refusal — keep the grounded
            // answer and simply drop this sentence. A refusal is the first/only sentence (nothing
            // voiced yet) and still falls through to the hand-off below. UNGROUNDED (a DEC-002
            // ungrounded amount) ALWAYS blocks, whatever was voiced, so no fabricated amount leaks.
            if (decision.verdict() == GuardrailDecision.Verdict.LOW_CONFIDENCE && !voiced.isEmpty()) {
                truncatedAfterGrounded = true;
                return;
            }
            blocked = true;
            fallbackMessage = decision.fallbackMessage();
            blockedVerdict = decision.verdict();
            return;
        }
        onChunk.accept(sentence);
        appendVoiced(sentence);
    }

    // Stop consuming further tokens either on a hard block (fallback) or once a trailing courtesy
    // hand-off was dropped after grounded content (BUG-024).
    private boolean stopped() {
        return blocked || truncatedAfterGrounded;
    }

    // Non-null after finish() when the turn ended on a fallback (DEC-002 block or empty low-confidence),
    // so the caller can record the guardrail-block metric on the streamed path.
    public GuardrailDecision.Verdict blockedVerdict() {
        return blockedVerdict;
    }

    private void appendVoiced(String sentence) {
        if (!voiced.isEmpty()) {
            voiced.append(' ');
        }
        voiced.append(sentence);
    }
}
