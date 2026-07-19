package com.voicesupport.shared.observability;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.ServletRequest;
import jakarta.servlet.ServletResponse;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.slf4j.MDC;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.mock.web.MockHttpServletResponse;

import java.io.IOException;
import java.util.UUID;
import java.util.concurrent.atomic.AtomicReference;

import static org.junit.jupiter.api.Assertions.assertDoesNotThrow;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

@DisplayName("CorrelationIdFilter (request id continuity)")
class CorrelationIdFilterTest {

    private final CorrelationIdFilter filter = new CorrelationIdFilter();

    @Test
    @DisplayName("reuses an inbound X-Correlation-Id header and echoes it, exposing it in the MDC")
    void reusesInboundHeader() throws Exception {
        // GIVEN a request carrying an upstream correlation id
        MockHttpServletRequest request = new MockHttpServletRequest();
        request.addHeader(CorrelationId.HEADER, "corr-inbound");
        MockHttpServletResponse response = new MockHttpServletResponse();
        AtomicReference<String> seenDuringChain = new AtomicReference<>();

        // WHEN the filter runs
        filter.doFilter(request, response, capturingChain(seenDuringChain));

        // THEN the id is visible to downstream logs and echoed on the response
        assertEquals("corr-inbound", seenDuringChain.get());
        assertEquals("corr-inbound", response.getHeader(CorrelationId.HEADER));
    }

    @Test
    @DisplayName("generates a correlation id when none is provided")
    void generatesWhenMissing() throws Exception {
        // GIVEN a request without a correlation id
        MockHttpServletRequest request = new MockHttpServletRequest();
        MockHttpServletResponse response = new MockHttpServletResponse();
        AtomicReference<String> seenDuringChain = new AtomicReference<>();

        // WHEN the filter runs
        filter.doFilter(request, response, capturingChain(seenDuringChain));

        // THEN a valid generated id is exposed and echoed
        assertNotNull(seenDuringChain.get());
        assertDoesNotThrow(() -> UUID.fromString(seenDuringChain.get()));
        assertEquals(seenDuringChain.get(), response.getHeader(CorrelationId.HEADER));
    }

    @Test
    @DisplayName("always clears the MDC after the request, even on downstream failure")
    void clearsMdcAfterRequest() {
        // GIVEN a chain that fails
        MockHttpServletRequest request = new MockHttpServletRequest();
        MockHttpServletResponse response = new MockHttpServletResponse();

        // WHEN the filter runs and the chain throws
        try {
            filter.doFilter(request, response, (req, res) -> {
                throw new ServletException("downstream boom");
            });
        } catch (Exception ignored) {
            // expected
        }

        // THEN no correlation id leaks onto the next request's thread
        assertNull(MDC.get(CorrelationId.MDC_KEY));
        assertTrue(response.getHeader(CorrelationId.HEADER) != null);
    }

    private FilterChain capturingChain(AtomicReference<String> seen) {
        return new FilterChain() {
            @Override
            public void doFilter(ServletRequest req, ServletResponse res) throws IOException, ServletException {
                seen.set(MDC.get(CorrelationId.MDC_KEY));
            }
        };
    }
}
