package com.voicesupport.shared.web.security;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.config.annotation.InterceptorRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

// Registers the api-key gate on the knowledge ingestion/sync, answer and retrieve paths that had
// no authentication before TASK-BE-019. Reads the shared secret directly (no injected @Component)
// so @WebMvcTest slices that auto-load this WebMvcConfigurer resolve cleanly and stay open when no
// key is set. The converse endpoints keep their own inline gate (same rule via ApiKeyGuard) and are
// intentionally not listed here to preserve their documented empty-body 401 contract. Health stays
// open for liveness probes.
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
                        "/api/conversation/retrieve");
    }
}
