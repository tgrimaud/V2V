package com.voicesupport.shared.observability;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.slf4j.MDC;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

import java.io.IOException;
import java.util.UUID;

// Establishes a request correlation id for every HTTP request (TASK-BE-009): reuses an
// inbound X-Correlation-Id header when present, otherwise generates one. The id is placed in
// the MDC (so all structured logs carry it) and echoed on the response header for continuity.
// Endpoints that receive an authoritative id in the request body (e.g. /converse) override it
// via CorrelationId.set; this filter still guarantees an id exists and is always cleared.
@Component
@Order(1)
public class CorrelationIdFilter extends OncePerRequestFilter {

    @Override
    protected void doFilterInternal(HttpServletRequest request, HttpServletResponse response, FilterChain chain)
            throws ServletException, IOException {
        String correlationId = resolve(request.getHeader(CorrelationId.HEADER));
        MDC.put(CorrelationId.MDC_KEY, correlationId);
        // Echo up front (before the response is committed). Endpoints that carry an
        // authoritative id in the body (e.g. /converse) override this header themselves.
        response.setHeader(CorrelationId.HEADER, correlationId);
        try {
            chain.doFilter(request, response);
        } finally {
            MDC.remove(CorrelationId.MDC_KEY);
            CorrelationId.clearChannel();
        }
    }

    private String resolve(String headerValue) {
        return headerValue == null || headerValue.isBlank() ? UUID.randomUUID().toString() : headerValue.trim();
    }
}
