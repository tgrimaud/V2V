package com.voicesupport.shared.web.security;

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

    public boolean authorized(String providedKey) {
        return apiKey == null || apiKey.isBlank() || apiKey.equals(providedKey);
    }

    public boolean isEnforced() {
        return apiKey != null && !apiKey.isBlank();
    }
}
