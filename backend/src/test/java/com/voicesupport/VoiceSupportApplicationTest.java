package com.voicesupport;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

import java.security.Security;

import static org.junit.jupiter.api.Assertions.assertEquals;

@DisplayName("VoiceSupportApplication (BUG-014 JVM DNS hardening)")
class VoiceSupportApplicationTest {

    private String previous;

    @AfterEach
    void restore() {
        // Restore whatever the property was before the test to avoid cross-test leakage.
        if (previous != null) {
            Security.setProperty("networkaddress.cache.negative.ttl", previous);
        }
    }

    @Test
    @DisplayName("hardenDnsCaching disables negative DNS caching so a stale lookup self-heals")
    void hardenDnsCachingSetsNegativeTtlToZero() {
        // GIVEN the current negative-TTL setting captured for restore
        previous = Security.getProperty("networkaddress.cache.negative.ttl");

        // WHEN the application hardens DNS caching
        VoiceSupportApplication.hardenDnsCaching();

        // THEN negative DNS results are never cached (0)
        assertEquals("0", Security.getProperty("networkaddress.cache.negative.ttl"));
    }
}
