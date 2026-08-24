package com.voicesupport.shared.http;

import org.springframework.http.HttpRequest;
import org.springframework.http.client.ClientHttpRequestExecution;
import org.springframework.http.client.ClientHttpRequestInterceptor;
import org.springframework.http.client.ClientHttpResponse;

import java.io.IOException;
import java.net.ConnectException;
import java.net.UnknownHostException;

// BUG-014: a bounded retry on *name-resolution / connect* failures only (UnknownHostException,
// ConnectException — the churn scenario). Combined with a zero negative-DNS-TTL
// (VoiceSupportApplication), a single stale name lookup during container/network churn self-heals
// on the immediate retry instead of failing the turn. Safe for the embedding call: embedding is a
// pure, side-effect-free read, so re-executing is idempotent. Read timeouts (SocketTimeoutException
// on a slow-but-reachable Ollama) are NOT retried, so a hung server is not made twice as slow —
// especially on the long-timeout KB-sync path.
public final class RetryingClientHttpRequestInterceptor implements ClientHttpRequestInterceptor {

    private final int maxAttempts;

    public RetryingClientHttpRequestInterceptor(int maxAttempts) {
        this.maxAttempts = Math.max(1, maxAttempts);
    }

    @Override
    public ClientHttpResponse intercept(
            HttpRequest request, byte[] body, ClientHttpRequestExecution execution) throws IOException {
        IOException last = null;
        for (int attempt = 1; attempt <= maxAttempts; attempt++) {
            try {
                return execution.execute(request, body);
            } catch (IOException failure) {
                if (!isReconnectable(failure)) {
                    throw failure;
                }
                last = failure;
            }
        }
        throw last;
    }

    // Retry only when the failure (or its cause chain) is a DNS/connect problem.
    private static boolean isReconnectable(IOException failure) {
        for (Throwable t = failure; t != null; t = t.getCause()) {
            if (t instanceof UnknownHostException || t instanceof ConnectException) {
                return true;
            }
        }
        return false;
    }
}
