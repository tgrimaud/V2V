package com.voicesupport.shared.observability;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.slf4j.MDC;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

@DisplayName("CorrelationId (client-controlled id/channel sanitization, TASK-BE-022 #3)")
class CorrelationIdTest {

    @AfterEach
    void clearMdc() {
        MDC.clear();
    }

    @Test
    @DisplayName("sanitize strips CR/LF so a crafted id cannot forge extra log lines")
    void sanitizeStripsControlChars() {
        // GIVEN a correlation id laced with a forged log line via CR/LF
        String malicious = "abc\r\n[CONVERSE] channel=admin grounded=true";

        // WHEN it is sanitized
        String clean = CorrelationId.sanitize(malicious);

        // THEN no carriage return or line feed survives (single log line preserved)
        assertFalse(clean.contains("\r"), "carriage return must be stripped");
        assertFalse(clean.contains("\n"), "line feed must be stripped");
        assertEquals("abc[CONVERSE] channel=admin grounded=true", clean);
    }

    @Test
    @DisplayName("sanitize caps the length so a huge id cannot bloat the MDC/response header")
    void sanitizeCapsLength() {
        // GIVEN an oversized correlation id
        String oversized = "x".repeat(5_000);

        // WHEN it is sanitized
        String clean = CorrelationId.sanitize(oversized);

        // THEN it is bounded to the 200-char ceiling
        assertEquals(200, clean.length());
    }

    @Test
    @DisplayName("sanitize preserves a normal id, trims surrounding whitespace, and maps null to null")
    void sanitizePreservesNormalId() {
        // GIVEN / WHEN / THEN a UUID-like value is unchanged, whitespace is trimmed, null stays null
        assertEquals("7f3c-uuid-like_id.42", CorrelationId.sanitize("  7f3c-uuid-like_id.42  "));
        assertNull(CorrelationId.sanitize(null));
    }

    @Test
    @DisplayName("set() sanitizes before the id reaches the MDC (structured logs)")
    void setSanitizesIntoMdc() {
        // GIVEN a body-supplied id carrying a CR/LF payload
        // WHEN it is set as the request correlation id
        CorrelationId.set("real-id\r\ninjected");

        // THEN the MDC value (used by every structured log line) is clean and single-line
        String stored = MDC.get(CorrelationId.MDC_KEY);
        assertEquals("real-idinjected", stored);
        assertFalse(stored.contains("\n"));
    }

    @Test
    @DisplayName("setChannel() sanitizes and falls back to n/a for a blank channel")
    void setChannelSanitizesAndDefaults() {
        // GIVEN a channel with an injected newline and, separately, a blank channel
        // WHEN each is set
        CorrelationId.setChannel("web\nphone");
        assertEquals("webphone", MDC.get(CorrelationId.CHANNEL_MDC_KEY));

        CorrelationId.setChannel("   ");
        // THEN a blank channel yields the safe default rather than an empty MDC entry
        assertEquals("n/a", MDC.get(CorrelationId.CHANNEL_MDC_KEY));
        assertTrue(CorrelationId.currentChannel().equals("n/a"));
    }
}
