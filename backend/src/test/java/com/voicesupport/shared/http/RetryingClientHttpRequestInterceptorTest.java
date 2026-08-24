package com.voicesupport.shared.http;

import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpRequest;
import org.springframework.http.client.ClientHttpRequestExecution;
import org.springframework.http.client.ClientHttpResponse;

import java.io.IOException;
import java.net.ConnectException;
import java.net.SocketTimeoutException;
import java.net.UnknownHostException;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertSame;
import static org.junit.jupiter.api.Assertions.assertThrows;

@DisplayName("RetryingClientHttpRequestInterceptor (BUG-014 bounded embedding retry)")
class RetryingClientHttpRequestInterceptorTest {

    @Test
    @DisplayName("retries once and succeeds when the first attempt fails with a stale DNS lookup")
    void retriesAfterTransientUnknownHost() throws IOException {
        // GIVEN an execution that throws UnknownHostException once, then succeeds
        ClientHttpResponse ok = new StubResponse();
        CountingExecution execution = new CountingExecution(
                new UnknownHostException("ollama"), ok);
        RetryingClientHttpRequestInterceptor interceptor = new RetryingClientHttpRequestInterceptor(2);

        // WHEN the request is intercepted
        ClientHttpResponse response = interceptor.intercept(null, new byte[0], execution);

        // THEN the retry re-resolved and returned the successful response after 2 attempts
        assertSame(ok, response);
        assertEquals(2, execution.attempts);
    }

    @Test
    @DisplayName("re-throws the last connect failure after exhausting the bounded attempts")
    void rethrowsAfterMaxAttempts() {
        // GIVEN an execution that always fails to connect
        CountingExecution execution = new CountingExecution(new ConnectException("refused"), null);
        RetryingClientHttpRequestInterceptor interceptor = new RetryingClientHttpRequestInterceptor(2);

        // WHEN / THEN it retries up to the cap then propagates the failure
        assertThrows(IOException.class,
                () -> interceptor.intercept(null, new byte[0], execution));
        assertEquals(2, execution.attempts);
    }

    @Test
    @DisplayName("does NOT retry a read timeout (slow-but-reachable Ollama is not made twice as slow)")
    void doesNotRetryReadTimeout() {
        // GIVEN a read timeout (server reachable but slow) that would recur
        CountingExecution execution = new CountingExecution(new SocketTimeoutException("read timed out"), null);
        RetryingClientHttpRequestInterceptor interceptor = new RetryingClientHttpRequestInterceptor(2);

        // WHEN / THEN it fails on the first attempt without retrying
        assertThrows(SocketTimeoutException.class,
                () -> interceptor.intercept(null, new byte[0], execution));
        assertEquals(1, execution.attempts);
    }

    @Test
    @DisplayName("maxAttempts below 1 is clamped to a single attempt (no retry)")
    void clampsToSingleAttempt() {
        // GIVEN a non-positive attempt count and a connect failure that could be retried
        CountingExecution execution = new CountingExecution(new ConnectException("refused"), null);
        RetryingClientHttpRequestInterceptor interceptor = new RetryingClientHttpRequestInterceptor(0);

        // WHEN / THEN exactly one attempt is made
        assertThrows(IOException.class,
                () -> interceptor.intercept(null, new byte[0], execution));
        assertEquals(1, execution.attempts);
    }

    // Fails with `failure` until the success attempt is reached, then returns `success`.
    private static final class CountingExecution implements ClientHttpRequestExecution {
        private final IOException failure;
        private final ClientHttpResponse success;
        private int attempts;

        CountingExecution(IOException failure, ClientHttpResponse success) {
            this.failure = failure;
            this.success = success;
        }

        @Override
        public ClientHttpResponse execute(HttpRequest request, byte[] body) throws IOException {
            attempts++;
            if (success != null && attempts >= 2) {
                return success;
            }
            throw failure;
        }
    }

    private static final class StubResponse implements ClientHttpResponse {
        @Override
        public org.springframework.http.HttpStatusCode getStatusCode() {
            return org.springframework.http.HttpStatus.OK;
        }

        @Override
        public String getStatusText() {
            return "OK";
        }

        @Override
        public void close() {
        }

        @Override
        public java.io.InputStream getBody() {
            return java.io.InputStream.nullInputStream();
        }

        @Override
        public org.springframework.http.HttpHeaders getHeaders() {
            return new org.springframework.http.HttpHeaders();
        }
    }
}
