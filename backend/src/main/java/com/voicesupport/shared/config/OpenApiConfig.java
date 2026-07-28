package com.voicesupport.shared.config;

import io.swagger.v3.oas.models.Components;
import io.swagger.v3.oas.models.OpenAPI;
import io.swagger.v3.oas.models.headers.Header;
import io.swagger.v3.oas.models.info.Info;
import io.swagger.v3.oas.models.info.License;
import io.swagger.v3.oas.models.media.StringSchema;
import io.swagger.v3.oas.models.parameters.HeaderParameter;
import io.swagger.v3.oas.models.responses.ApiResponse;
import io.swagger.v3.oas.models.security.SecurityScheme;
import org.springdoc.core.customizers.OperationCustomizer;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

// OpenAPI 3 metadata for the backend REST surface (TASK-BE-016). Serves /v3/api-docs +
// Swagger UI. JSON field names follow the global snake_case Jackson strategy (JacksonConfig),
// so the generated schemas already read snake_case. The correlation-id contract (shared by
// every endpoint, TASK-BE-009) is applied once here via an OperationCustomizer instead of
// annotating each controller method.
@Configuration
public class OpenApiConfig {

    static final String CORRELATION_ID_HEADER = "X-Correlation-Id";
    static final String API_KEY_SCHEME = "apiKey";
    private static final String API_KEY_HEADER = "x-api-key";

    @Bean
    public OpenAPI voiceSupportOpenApi(@Value("${voice-support.api.version:0.1.0}") String version) {
        return new OpenAPI()
                .info(apiInfo(version))
                .components(new Components().addSecuritySchemes(API_KEY_SCHEME, apiKeyScheme()));
    }

    private Info apiInfo(String version) {
        return new Info()
                .title("Voice Support Bot — Backend API")
                .version(version)
                .description("RAG answer engine for the operator support voice assistant: knowledge-base "
                        + "sync/ingestion and the conversation endpoints the voice runtime calls "
                        + "(retrieve, answer, converse, converse-stream). JSON is snake_case; every "
                        + "response echoes the `" + CORRELATION_ID_HEADER + "` header, and errors use the "
                        + "sanitized `{error_code, message, correlation_id}` contract.")
                .license(new License().name("Proprietary"));
    }

    private SecurityScheme apiKeyScheme() {
        return new SecurityScheme()
                .type(SecurityScheme.Type.APIKEY)
                .in(SecurityScheme.In.HEADER)
                .name(API_KEY_HEADER)
                .description("Optional shared secret. Required only when "
                        + "`voice-support.conversation.api-key` is configured (pilot: open).");
    }

    // Correlation id is a cross-cutting contract on every endpoint: an optional request header
    // that is always echoed on the response (CorrelationIdFilter). Documented once for all ops.
    @Bean
    public OperationCustomizer correlationIdCustomizer() {
        return (operation, handlerMethod) -> {
            operation.addParametersItem(correlationIdRequestParam());
            operation.getResponses().forEach((code, response) -> addCorrelationIdHeader(response));
            return operation;
        };
    }

    private HeaderParameter correlationIdRequestParam() {
        return (HeaderParameter) new HeaderParameter()
                .name(CORRELATION_ID_HEADER)
                .description("Optional correlation id propagated across logs, metrics and the response. "
                        + "Generated when absent.")
                .required(false)
                .schema(new StringSchema());
    }

    private void addCorrelationIdHeader(ApiResponse response) {
        response.addHeaderObject(CORRELATION_ID_HEADER, new Header()
                .description("Correlation id for this request (client-supplied or generated).")
                .schema(new StringSchema()));
    }
}
