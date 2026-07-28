package com.voicesupport.shared.web.security;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;

// Single source of truth for the shared-secret rule (TASK-BE-019, ADR-0021). When a
// key is configured, callers must present a matching x-api-key header; an empty/blank key keeps
// endpoints open for the localhost pilot. Kept as a plain (non-Spring) class so slice tests
// (@WebMvcTest) that auto-load the registering WebMvcConfigurer do not need an extra bean; it is
// constructed from configuration in WebSecurityMvcConfig.
public class ApiKeyGuard {

    private final String apiKey;

    public ApiKeyGuard(String apiKey) {
        this.apiKey = apiKey;
    }

    // Constant-time comparison (MessageDigest.isEqual): a plain String.equals short-circuits on
    // the first differing byte, leaking the shared secret one byte at a time through response
    // timing. This is a security gate, so the compare must not depend on how much of the key matches.
    public boolean authorized(String providedKey) {
        if (apiKey == null || apiKey.isBlank()) {
            return true;
        }
        if (providedKey == null) {
            return false;
        }
        return MessageDigest.isEqual(
                apiKey.getBytes(StandardCharsets.UTF_8),
                providedKey.getBytes(StandardCharsets.UTF_8));
    }
}
