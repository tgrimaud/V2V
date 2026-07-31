package com.voicesupport.conversation.application.service;

import com.voicesupport.conversation.domain.model.valueobject.AnswerLanguage;
import com.voicesupport.conversation.domain.model.valueobject.RetrievedEvidence;
import com.voicesupport.conversation.domain.port.in.WarmUpUseCase;
import com.voicesupport.conversation.domain.port.out.AnswerGeneratorPort;
import com.voicesupport.conversation.domain.port.out.KnowledgeRetrievalPort;
import com.voicesupport.conversation.domain.model.valueobject.WarmUpResult;
import com.voicesupport.shared.observability.BackendTelemetry;

import java.time.Duration;
import java.util.List;

// Connect-time model warm-up for the voice latency levers (TASK-BE-017 / TASK-WEB-021, ADR-0037).
// Exercises the embedding (retrieval) and the LLM once so the first real turn is warm. It touches
// NO conversation memory (no ConversationMemoryPort dependency) and discards the generated text, so
// it is side-effect-free and safe to call repeatedly. A failing step never throws: it is recorded
// as a warm-up miss so a cold provider can never block or delay the caller's first real turn.
public class WarmUpService implements WarmUpUseCase {

    private static final String PROVIDER = "warmup";
    private static final String SLICE_EMBEDDING = "warmup_embedding";
    private static final String SLICE_LLM = "warmup_llm";
    private static final String SUCCESS = "success";
    private static final String ERROR = "error";
    private static final int WARM_TOP_K = 1;

    private final KnowledgeRetrievalPort retrieval;
    private final AnswerGeneratorPort generator;
    private final BackendTelemetry telemetry;
    private final String warmQuery;
    private final AnswerLanguage language;

    public WarmUpService(KnowledgeRetrievalPort retrieval, AnswerGeneratorPort generator,
            BackendTelemetry telemetry, String warmQuery, AnswerLanguage language) {
        this.retrieval = retrieval;
        this.generator = generator;
        this.telemetry = telemetry;
        this.warmQuery = warmQuery;
        this.language = language;
    }

    @Override
    public WarmUpResult warmUp() {
        long start = System.nanoTime();
        List<RetrievedEvidence> evidence = warmEmbedding();
        boolean llmWarmed = warmLlm(evidence);
        return new WarmUpResult(evidence != null, llmWarmed, millisSince(start));
    }

    private List<RetrievedEvidence> warmEmbedding() {
        long start = System.nanoTime();
        try {
            List<RetrievedEvidence> evidence = retrieval.retrieve(warmQuery, null, WARM_TOP_K);
            telemetry.recordLatency(SLICE_EMBEDDING, PROVIDER, SUCCESS, elapsed(start));
            return evidence;
        } catch (RuntimeException e) {
            telemetry.recordLatency(SLICE_EMBEDDING, PROVIDER, ERROR, elapsed(start));
            return null;
        }
    }

    private boolean warmLlm(List<RetrievedEvidence> evidence) {
        long start = System.nanoTime();
        try {
            generator.generate(warmQuery, evidence == null ? List.of() : evidence, List.of(), language);
            telemetry.recordLatency(SLICE_LLM, PROVIDER, SUCCESS, elapsed(start));
            return true;
        } catch (RuntimeException e) {
            telemetry.recordLatency(SLICE_LLM, PROVIDER, ERROR, elapsed(start));
            return false;
        }
    }

    private Duration elapsed(long startNanos) {
        return Duration.ofNanos(System.nanoTime() - startNanos);
    }

    private long millisSince(long startNanos) {
        return elapsed(startNanos).toMillis();
    }
}
