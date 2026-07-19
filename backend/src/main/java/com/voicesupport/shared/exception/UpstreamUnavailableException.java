package com.voicesupport.shared.exception;

// Raised when a backend dependency the answer engine relies on (LLM provider, embedding
// endpoint, vector store) is unavailable or times out (TASK-BE-012). Carries a short,
// non-sensitive reason for server-side logs; GlobalExceptionHandler maps it to a sanitized
// 503 ERR_UPSTREAM response that never echoes the underlying cause to the client.
public class UpstreamUnavailableException extends RuntimeException {

    public UpstreamUnavailableException(String message) {
        super(message);
    }

    public UpstreamUnavailableException(String message, Throwable cause) {
        super(message, cause);
    }
}
