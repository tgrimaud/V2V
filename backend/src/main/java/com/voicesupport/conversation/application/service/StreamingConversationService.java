package com.voicesupport.conversation.application.service;

import com.voicesupport.conversation.domain.model.TokenStream;
import com.voicesupport.conversation.domain.model.valueobject.AnswerLanguage;
import com.voicesupport.conversation.domain.model.valueobject.ConversationTurn;
import com.voicesupport.conversation.domain.model.valueobject.GeneratedAnswer;
import com.voicesupport.conversation.domain.model.valueobject.GroundingResult;
import com.voicesupport.conversation.domain.model.valueobject.GuardrailDecision;
import com.voicesupport.conversation.domain.model.valueobject.RetrievedEvidence;
import com.voicesupport.conversation.domain.port.in.ConverseStreamUseCase;
import com.voicesupport.conversation.domain.port.in.GroundQueryUseCase;
import com.voicesupport.conversation.domain.port.out.ConversationMemoryPort;
import com.voicesupport.conversation.domain.port.out.StreamingAnswerGeneratorPort;
import com.voicesupport.conversation.domain.service.ConversationHistoryFormatter;
import com.voicesupport.conversation.domain.service.GuardedSentenceEmitter;
import com.voicesupport.conversation.domain.service.LanguageDetector;
import com.voicesupport.conversation.domain.service.OutputGuardrail;
import com.voicesupport.shared.observability.BackendTelemetry;

import java.util.List;
import java.util.function.Consumer;

// Streaming counterpart of ConversationService (TASK-BE-007, ADR-0013): the same
// ground -> LLM -> output-guardrail -> memory pipeline, but the LLM step streams and each
// sentence is guardrail-vetted before emission (GuardedSentenceEmitter), so DEC-002 holds on the
// streamed path. The pipeline runs when the returned TokenStream is consumed; memory records the
// final voiced answer exactly like the sync path. A blocked grounding decision yields a spoken
// fallback with no LLM call.
public class StreamingConversationService implements ConverseStreamUseCase {

    private final GroundQueryUseCase groundQueryUseCase;
    private final StreamingAnswerGeneratorPort streamingGenerator;
    private final OutputGuardrail outputGuardrail;
    private final ConversationMemoryPort memory;
    private final LanguageDetector languageDetector;
    private final BackendTelemetry telemetry;
    // Retrieval top-K for the streaming voice path (TASK-BE-011): configurable so the RAG context
    // size (a driver of LLM time-to-first-token) can be tuned without a code change.
    private final int topK;

    public StreamingConversationService(
            GroundQueryUseCase groundQueryUseCase,
            StreamingAnswerGeneratorPort streamingGenerator,
            OutputGuardrail outputGuardrail,
            ConversationMemoryPort memory,
            LanguageDetector languageDetector,
            BackendTelemetry telemetry,
            int topK) {
        this.groundQueryUseCase = groundQueryUseCase;
        this.streamingGenerator = streamingGenerator;
        this.outputGuardrail = outputGuardrail;
        this.memory = memory;
        this.languageDetector = languageDetector;
        this.telemetry = telemetry;
        this.topK = topK;
    }

    @Override
    public TokenStream converseStream(String transcript, String conversationId) {
        return converseStream(transcript, conversationId, null);
    }

    @Override
    public TokenStream converseStream(String transcript, String conversationId, String forcedLanguage) {
        return onChunk -> runPipeline(transcript, conversationId, forcedLanguage, onChunk);
    }

    private GeneratedAnswer runPipeline(
            String transcript, String conversationId, String forcedLanguage, Consumer<String> onChunk) {
        List<ConversationTurn> prior = memory.recentTurns(conversationId);
        List<String> history = ConversationHistoryFormatter.format(prior);
        AnswerLanguage language = languageDetector.resolve(transcript, history, forcedLanguage);
        // BUG-007: null domain = search ALL domains ON PURPOSE. There is no runtime classifier of
        // the incoming QUESTION on the voice path (ADR-0015 not implemented); the DomainClassifierPort
        // (ADR-0030) only tags KB articles at ingestion, so no reliable per-question domain can be
        // supplied and forcing one could drop relevant chunks. Audience fail-closed (ADR-0034) +
        // per-sentence guardrails still keep the streamed answer DEC-002-safe. Cross-domain precision
        // trade-off tracked in OQ-008. See ConversationService.
        GroundingResult grounding = groundQueryUseCase.ground(transcript, null, topK, !prior.isEmpty(), language);
        GeneratedAnswer answer = grounding.answerable()
                ? streamGrounded(transcript, grounding, history, language, onChunk)
                : emitFallback(language, grounding.decision(), onChunk);
        memory.append(conversationId, new ConversationTurn(transcript, answer.text()));
        return answer;
    }

    private GeneratedAnswer streamGrounded(
            String question, GroundingResult grounding, List<String> history,
            AnswerLanguage language, Consumer<String> onChunk) {
        List<RetrievedEvidence> evidence = grounding.evidence();
        GuardedSentenceEmitter emitter = new GuardedSentenceEmitter(
                evidence, outputGuardrail, onChunk, bestScore(evidence), language);
        streamingGenerator.generate(question, evidence, history, language, emitter::accept);
        return emitter.finish();
    }

    private GeneratedAnswer emitFallback(AnswerLanguage language, GuardrailDecision decision, Consumer<String> onChunk) {
        // Guardrail-fallback turns skip the streaming LLM, so record the answer language here (no
        // provider) to keep per-turn language observability complete on the voice path (TASK-BE-015),
        // plus the blocked verdict so clarify/low-confidence rates are observable (ADR-0034).
        telemetry.recordGuardrailBlock(decision.verdict().name());
        telemetry.recordAnswerLanguage(null, language.code());
        String message = decision.fallbackMessage();
        onChunk.accept(message);
        return GeneratedAnswer.fallback(message);
    }

    private double bestScore(List<RetrievedEvidence> evidence) {
        return evidence.stream().mapToDouble(RetrievedEvidence::score).max().orElse(0.0);
    }
}
