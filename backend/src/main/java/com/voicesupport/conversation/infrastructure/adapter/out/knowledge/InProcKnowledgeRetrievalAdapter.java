package com.voicesupport.conversation.infrastructure.adapter.out.knowledge;

import com.voicesupport.conversation.domain.model.valueobject.RetrievedEvidence;
import com.voicesupport.conversation.domain.port.out.KnowledgeRetrievalPort;
import com.voicesupport.knowledge.domain.model.valueobject.KnowledgeChunk;
import com.voicesupport.knowledge.domain.port.in.KnowledgeRetrievalUseCase;
import com.voicesupport.shared.exception.UpstreamUnavailableException;
import com.voicesupport.shared.observability.BackendTelemetry;
import com.voicesupport.shared.observability.Slices;

import java.time.Duration;
import java.util.List;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Future;
import java.util.concurrent.RejectedExecutionException;
import java.util.concurrent.SynchronousQueue;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;

// Outbound retrieval seam (RETRIEVAL slice). Bounds the whole retrieve() call — the Ollama query
// embedding (its own HTTP timeout, TASK-BE-025) PLUS the pgvector similaritySearch SQL — with a
// wall-clock budget so a slow/locked DB query fails fast into the sanitized ERR_UPSTREAM path
// instead of holding the request/SSE worker until upstream timeouts (TASK-BE-025 acceptance:
// "a slow embedding/pgvector call fails fast within a configured budget").
//
// The bound is enforced by a bounded executor (like the LLM sync path): future.get(budget) frees
// the caller and records a distinct `timeout` outcome. Residual: JDBC does not honour interrupt,
// so the abandoned SQL statement keeps running on a daemon thread until Postgres returns — a
// true DB-side cancel needs a Postgres `statement_timeout`/socketTimeout on the vector-store
// connection (shared with KB sync inserts), tracked as a follow-up. This fix removes the worker
// hang; the deeper DB cancel is deliberately out of this minimal scope.
public class InProcKnowledgeRetrievalAdapter implements KnowledgeRetrievalPort {

    private static final String PROVIDER = "pgvector";
    private static final String OUTCOME_SUCCESS = "success";
    private static final String OUTCOME_TIMEOUT = "timeout";
    private static final String OUTCOME_ERROR = "error";

    // Bounded pool mirroring the LLM executor: caps concurrent retrieval calls so a DB stall cannot
    // spawn unbounded threads; excess submissions are rejected and degrade to a sanitized 503.
    private static final int MAX_RETRIEVAL_THREADS = 16;
    private static final ExecutorService RETRIEVAL_EXECUTOR = new ThreadPoolExecutor(
            0, MAX_RETRIEVAL_THREADS, 60L, TimeUnit.SECONDS, new SynchronousQueue<>(),
            runnable -> {
                Thread thread = new Thread(runnable, "retrieval-call");
                thread.setDaemon(true);
                return thread;
            },
            new ThreadPoolExecutor.AbortPolicy());

    private final KnowledgeRetrievalUseCase knowledgeRetrieval;
    private final BackendTelemetry telemetry;
    // Overall retrieve() budget in ms (embedding + pgvector query). <= 0 disables the bound.
    private final long searchTimeoutMs;

    public InProcKnowledgeRetrievalAdapter(
            KnowledgeRetrievalUseCase knowledgeRetrieval, BackendTelemetry telemetry, long searchTimeoutMs) {
        this.knowledgeRetrieval = knowledgeRetrieval;
        this.telemetry = telemetry;
        this.searchTimeoutMs = searchTimeoutMs;
    }

    @Override
    public List<RetrievedEvidence> retrieve(String query, String domain, int topK) {
        long start = System.nanoTime();
        String outcome = OUTCOME_SUCCESS;
        try {
            return bounded(query, domain, topK);
        } catch (TimeoutException e) {
            outcome = OUTCOME_TIMEOUT;
            throw new UpstreamUnavailableException(
                    "Knowledge retrieval timed out after " + searchTimeoutMs + " ms", e);
        } catch (RuntimeException e) {
            outcome = OUTCOME_ERROR;
            throw e;
        } finally {
            telemetry.recordLatency(Slices.RETRIEVAL, PROVIDER, outcome, Duration.ofNanos(System.nanoTime() - start));
        }
    }

    private List<RetrievedEvidence> bounded(String query, String domain, int topK) throws TimeoutException {
        if (searchTimeoutMs <= 0) {
            return doRetrieve(query, domain, topK);
        }
        Future<List<RetrievedEvidence>> future;
        try {
            future = RETRIEVAL_EXECUTOR.submit(() -> doRetrieve(query, domain, topK));
        } catch (RejectedExecutionException e) {
            throw new UpstreamUnavailableException("Knowledge retrieval concurrency limit reached", e);
        }
        try {
            return future.get(searchTimeoutMs, TimeUnit.MILLISECONDS);
        } catch (TimeoutException e) {
            future.cancel(true);
            throw e;
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            throw new UpstreamUnavailableException("Knowledge retrieval interrupted", e);
        } catch (ExecutionException e) {
            throw asRuntime(e.getCause());
        }
    }

    private List<RetrievedEvidence> doRetrieve(String query, String domain, int topK) {
        return knowledgeRetrieval.retrieve(query, domain, topK).stream()
                .map(InProcKnowledgeRetrievalAdapter::toEvidence)
                .toList();
    }

    private static RuntimeException asRuntime(Throwable cause) {
        if (cause instanceof RuntimeException runtime) {
            return runtime;
        }
        return new UpstreamUnavailableException("Knowledge retrieval failed", cause);
    }

    private static RetrievedEvidence toEvidence(KnowledgeChunk chunk) {
        return new RetrievedEvidence(chunk.text(), chunk.sourceId(), chunk.domain(), chunk.score());
    }
}
