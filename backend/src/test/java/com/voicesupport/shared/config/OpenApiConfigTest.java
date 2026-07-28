package com.voicesupport.shared.config;

import io.swagger.v3.oas.models.OpenAPI;
import io.swagger.v3.oas.models.Operation;
import io.swagger.v3.oas.models.parameters.Parameter;
import io.swagger.v3.oas.models.responses.ApiResponse;
import io.swagger.v3.oas.models.responses.ApiResponses;
import io.swagger.v3.oas.models.security.SecurityScheme;
import org.junit.jupiter.api.Test;
import org.springdoc.core.customizers.OperationCustomizer;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

class OpenApiConfigTest {

    private final OpenApiConfig config = new OpenApiConfig();

    @Test
    void openApiBeanExposesInfoAndApiKeyScheme() {
        // GIVEN the OpenAPI bean built with an explicit version
        OpenAPI api = config.voiceSupportOpenApi("9.9.9");

        // THEN the info and the optional api-key header scheme are described
        assertEquals("Voice Support Bot — Backend API", api.getInfo().getTitle());
        assertEquals("9.9.9", api.getInfo().getVersion());
        SecurityScheme scheme = api.getComponents().getSecuritySchemes().get(OpenApiConfig.API_KEY_SCHEME);
        assertNotNull(scheme);
        assertEquals(SecurityScheme.Type.APIKEY, scheme.getType());
        assertEquals(SecurityScheme.In.HEADER, scheme.getIn());
        assertEquals("x-api-key", scheme.getName());
    }

    @Test
    void correlationIdCustomizerAddsRequestParamAndResponseHeader() {
        // GIVEN an operation carrying a single 200 response
        OperationCustomizer customizer = config.correlationIdCustomizer();
        Operation operation = new Operation().responses(
                new ApiResponses().addApiResponse("200", new ApiResponse().description("ok")));

        // WHEN the correlation-id customizer runs
        Operation result = customizer.customize(operation, null);

        // THEN the correlation id is documented as an optional request header and echoed on the response
        boolean hasHeaderParam = result.getParameters().stream()
                .anyMatch(p -> OpenApiConfig.CORRELATION_ID_HEADER.equals(p.getName())
                        && "header".equals(p.getIn())
                        && Boolean.FALSE.equals(requiredOrFalse(p)));
        assertTrue(hasHeaderParam, "expected an optional X-Correlation-Id header parameter");
        assertTrue(result.getResponses().get("200").getHeaders().containsKey(OpenApiConfig.CORRELATION_ID_HEADER),
                "expected the X-Correlation-Id response header");
    }

    private Boolean requiredOrFalse(Parameter parameter) {
        return parameter.getRequired() == null ? Boolean.FALSE : parameter.getRequired();
    }
}
