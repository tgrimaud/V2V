package com.voicesupport.shared.web.security;

import com.voicesupport.shared.config.JacksonConfig;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.context.annotation.Import;
import org.springframework.test.context.TestPropertySource;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

// TASK-BE-023: the OpenAPI docs (`/v3/api-docs`, `.yaml`, grouped) and the Swagger UI must not be
// anonymously enumerable once a shared secret is configured (non-localhost posture), while the
// localhost pilot / QA (no key) stays open. A tiny probe controller stands in for springdoc at the
// exact served paths so the WebSecurityMvcConfig interceptor mapping is exercised without pulling
// the springdoc auto-config into the slice.
@RestController
class DocsProbeController {

    @GetMapping({"/v3/api-docs", "/v3/api-docs.yaml"})
    String apiDocs() {
        return "spec";
    }

    @GetMapping("/v3/api-docs/public")
    String groupedApiDocs() {
        return "grouped-spec";
    }

    @GetMapping("/swagger-ui/index.html")
    String swaggerUi() {
        return "ui";
    }
}

@WebMvcTest(DocsProbeController.class)
@Import({JacksonConfig.class, WebSecurityMvcConfig.class})
@TestPropertySource(properties = "voice-support.conversation.api-key=s3cret")
@DisplayName("Ops surface (docs) is gated behind x-api-key when a key is configured (TASK-BE-023)")
class OpsSurfaceApiKeyTest {

    @Autowired
    private MockMvc mockMvc;

    @Test
    @DisplayName("GET /v3/api-docs without api-key is rejected with 401 + ErrorResponse")
    void apiDocsRejectedWithoutKey() throws Exception {
        mockMvc.perform(get("/v3/api-docs"))
                .andExpect(status().isUnauthorized())
                .andExpect(jsonPath("$.error_code").value("ERR_401"));
    }

    @Test
    @DisplayName("GET /v3/api-docs.yaml without api-key is rejected with 401")
    void apiDocsYamlRejectedWithoutKey() throws Exception {
        mockMvc.perform(get("/v3/api-docs.yaml"))
                .andExpect(status().isUnauthorized());
    }

    @Test
    @DisplayName("GET a grouped /v3/api-docs/** path without api-key is rejected with 401")
    void groupedApiDocsRejectedWithoutKey() throws Exception {
        mockMvc.perform(get("/v3/api-docs/public"))
                .andExpect(status().isUnauthorized());
    }

    @Test
    @DisplayName("GET /swagger-ui/index.html without api-key is rejected with 401")
    void swaggerUiRejectedWithoutKey() throws Exception {
        mockMvc.perform(get("/swagger-ui/index.html"))
                .andExpect(status().isUnauthorized());
    }

    @Test
    @DisplayName("GET /v3/api-docs with the matching api-key is served (200)")
    void apiDocsServedWithKey() throws Exception {
        mockMvc.perform(get("/v3/api-docs").header("x-api-key", "s3cret"))
                .andExpect(status().isOk());
    }

    @Test
    @DisplayName("GET /swagger-ui/index.html with the matching api-key is served (200)")
    void swaggerUiServedWithKey() throws Exception {
        mockMvc.perform(get("/swagger-ui/index.html").header("x-api-key", "s3cret"))
                .andExpect(status().isOk());
    }
}

@WebMvcTest(DocsProbeController.class)
@Import({JacksonConfig.class, WebSecurityMvcConfig.class})
@DisplayName("Ops surface (docs) stays open when no key is configured — localhost pilot (TASK-BE-023)")
class OpsSurfaceOpenWithoutKeyTest {

    @Autowired
    private MockMvc mockMvc;

    @Test
    @DisplayName("GET /v3/api-docs without a configured key is open (200) for the pilot")
    void apiDocsOpenWithoutConfiguredKey() throws Exception {
        mockMvc.perform(get("/v3/api-docs"))
                .andExpect(status().isOk());
    }

    @Test
    @DisplayName("GET /swagger-ui/index.html without a configured key is open (200) for the pilot")
    void swaggerUiOpenWithoutConfiguredKey() throws Exception {
        mockMvc.perform(get("/swagger-ui/index.html"))
                .andExpect(status().isOk());
    }
}
