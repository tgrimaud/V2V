package com.voicesupport.shared.web.security;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.config.annotation.InterceptorRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

// Registers the api-key gate on the knowledge ingestion/sync, answer, retrieve, warm-up and
// escalation hand-off fetch (TASK-BE-036) paths, plus the OpenAPI docs / Swagger UI surface
// (TASK-BE-023). Reads the shared secret directly (no injected @Component) so @WebMvcTest slices
// that auto-load this WebMvcConfigurer resolve cleanly and stay open when no key is set. The
// converse endpoints keep their own inline gate (same rule via ApiKeyGuard) and are intentionally
// not listed here to preserve their documented empty-body 401 contract. Health stays open for
// liveness probes (Actuator `metrics` is closed by exposure config, not by this interceptor).
//
// TASK-BE-023 (ops-surface hardening): with a key configured (non-localhost posture) the API
// contract (`/v3/api-docs`, `.yaml`, grouped) and the interactive Swagger UI are no longer
// anonymously enumerable — same `x-api-key` rule as the data endpoints, so the localhost pilot /
// QA (no key) stays frictionless while any keyed deployment is closed.
@Configuration
public class WebSecurityMvcConfig implements WebMvcConfigurer {

    private final ApiKeyGuard apiKeyGuard;
    private final ObjectMapper objectMapper;

    public WebSecurityMvcConfig(
            @Value("${voice-support.conversation.api-key:}") String apiKey,
            ObjectMapper objectMapper) {
        this.apiKeyGuard = new ApiKeyGuard(apiKey);
        this.objectMapper = objectMapper;
    }

    @Override
    public void addInterceptors(InterceptorRegistry registry) {
        registry.addInterceptor(new ApiKeyAuthInterceptor(apiKeyGuard, objectMapper))
                .addPathPatterns(
                        "/api/knowledge/**",
                        "/api/conversation/answer",
                        "/api/conversation/billing-explain",
                        "/api/conversation/retrieve",
                        "/api/conversation/warm-up",
                        "/api/conversation/escalation-handoffs/**",
                        // TASK-BE-023: OpenAPI docs + Swagger UI (open only when no key is set).
                        "/v3/api-docs",
                        "/v3/api-docs/**",
                        "/v3/api-docs.yaml",
                        "/swagger-ui.html",
                        "/swagger-ui/**");
    }
}
