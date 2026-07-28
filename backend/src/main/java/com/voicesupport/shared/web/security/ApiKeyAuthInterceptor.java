package com.voicesupport.shared.web.security;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.voicesupport.shared.observability.CorrelationId;
import com.voicesupport.shared.web.rest.ErrorResponse;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.web.servlet.HandlerInterceptor;

import java.io.IOException;

// Enforces the shared-secret gate on the ingestion/retrieval/answer paths that previously had no
// authentication (TASK-BE-019). Delegates the decision to ApiKeyGuard so the rule stays identical
// to the converse endpoints, but rejects unauthorized calls with the sanitized ErrorResponse
// contract (401 + correlation id) before any use case or side effect runs.
public class ApiKeyAuthInterceptor implements HandlerInterceptor {

    static final String HEADER = "x-api-key";

    private static final Logger log = LoggerFactory.getLogger(ApiKeyAuthInterceptor.class);
    private static final String ERR_401 = "ERR_401";
    private static final String MSG_401 = "A valid x-api-key header is required for this endpoint.";

    private final ApiKeyGuard apiKeyGuard;
    private final ObjectMapper objectMapper;

    public ApiKeyAuthInterceptor(ApiKeyGuard apiKeyGuard, ObjectMapper objectMapper) {
        this.apiKeyGuard = apiKeyGuard;
        this.objectMapper = objectMapper;
    }

    @Override
    public boolean preHandle(HttpServletRequest request, HttpServletResponse response, Object handler)
            throws IOException {
        if (apiKeyGuard.authorized(request.getHeader(HEADER))) {
            return true;
        }
        log.warn("[AUTH] rejected unauthenticated request method={} path={} correlation_id={}",
                request.getMethod(), request.getRequestURI(), CorrelationId.current());
        writeUnauthorized(response);
        return false;
    }

    private void writeUnauthorized(HttpServletResponse response) throws IOException {
        response.setStatus(HttpStatus.UNAUTHORIZED.value());
        response.setContentType(MediaType.APPLICATION_JSON_VALUE);
        ErrorResponse body = ErrorResponse.of(ERR_401, MSG_401, CorrelationId.current());
        objectMapper.writeValue(response.getWriter(), body);
    }
}
