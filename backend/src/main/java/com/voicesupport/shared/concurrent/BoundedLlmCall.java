package com.voicesupport.shared.concurrent;

import com.voicesupport.shared.exception.UpstreamUnavailableException;

import java.util.concurrent.ExecutorService;
import java.util.concurrent.Future;
import java.util.concurrent.RejectedExecutionException;
import java.util.concurrent.SynchronousQueue;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;
import java.util.function.Supplier;

// Bounded synchronous call executor (TASK-BE-012), extracted from AbstractChatClientAnswerAdapter to
// keep that adapter within the 200-line class budget. A cached pool would spawn one thread per
// concurrent call with no ceiling, so a provider stall could exhaust threads. This caps in-flight
// calls at MAX_LLM_THREADS; excess submissions are rejected and degrade to a sanitized 503
// (UpstreamUnavailableException) rather than piling up. The direct-handoff SynchronousQueue keeps
// latency low under normal load (no queueing) while enforcing the ceiling under overload. Lives in
// `shared` (cross-cutting, context-agnostic) so it depends on no bounded context.
public final class BoundedLlmCall {

    private static final int MAX_LLM_THREADS = 16;
    // Executor timeout is a backstop above the provider HTTP read timeout (LlmConfig): the socket
    // read timeout normally fires first and closes the connection cleanly, so this only trips if
    // the client hangs before the read (DNS/connect stall) — future.cancel then abandons it.
    private static final long TIMEOUT_BACKSTOP_MS = 2_000;
    private static final ExecutorService LLM_EXECUTOR = new ThreadPoolExecutor(
            0, MAX_LLM_THREADS, 60L, TimeUnit.SECONDS, new SynchronousQueue<>(),
            runnable -> {
                Thread thread = new Thread(runnable, "llm-call");
                thread.setDaemon(true);
                return thread;
            },
            new ThreadPoolExecutor.AbortPolicy());

    private BoundedLlmCall() {
    }

    public static String run(long timeoutMs, Supplier<String> work) {
        if (timeoutMs <= 0) {
            return work.get();
        }
        Future<String> future;
        try {
            future = LLM_EXECUTOR.submit(work::get);
        } catch (RejectedExecutionException e) {
            throw new UpstreamUnavailableException("LLM concurrency limit reached", e);
        }
        try {
            return future.get(timeoutMs + TIMEOUT_BACKSTOP_MS, TimeUnit.MILLISECONDS);
        } catch (TimeoutException e) {
            future.cancel(true);
            throw new UpstreamUnavailableException("LLM provider timed out after " + timeoutMs + " ms", e);
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            throw new UpstreamUnavailableException("LLM call interrupted", e);
        } catch (java.util.concurrent.ExecutionException e) {
            throw new UpstreamUnavailableException("LLM provider call failed", e.getCause());
        }
    }
}
