package com.voicesupport.shared.web.security;

import com.voicesupport.conversation.domain.model.valueobject.AnswerLanguage;
import com.voicesupport.conversation.domain.model.valueobject.GeneratedAnswer;
import com.voicesupport.conversation.domain.port.in.AnswerQuestionUseCase;
import com.voicesupport.conversation.domain.port.in.GroundQueryUseCase;
import com.voicesupport.conversation.domain.service.LanguageDetector;
import com.voicesupport.conversation.infrastructure.adapter.in.rest.AnswerController;
import com.voicesupport.conversation.infrastructure.adapter.in.rest.RetrievalController;
import com.voicesupport.knowledge.domain.port.in.IngestKnowledgeUseCase;
import com.voicesupport.knowledge.domain.port.in.SyncKnowledgeUseCase;
import com.voicesupport.knowledge.infrastructure.adapter.in.rest.KnowledgeController;
import com.voicesupport.shared.config.JacksonConfig;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Import;
import org.springframework.http.MediaType;
import org.springframework.mock.web.MockMultipartFile;
import org.springframework.test.context.TestPropertySource;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.multipart;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

// TASK-BE-019: the answer, retrieve and knowledge endpoints had no authentication. With a shared
// secret configured, the central ApiKeyAuthInterceptor must reject calls without a matching
// x-api-key before any use case runs, returning the sanitized ErrorResponse contract (401).
@WebMvcTest({AnswerController.class, RetrievalController.class, KnowledgeController.class})
@Import({JacksonConfig.class, WebSecurityMvcConfig.class})
@TestPropertySource(properties = "voice-support.conversation.api-key=s3cret")
@DisplayName("Protected endpoints require x-api-key (TASK-BE-019)")
class ProtectedEndpointsApiKeyTest {

    private static final String ANSWER_BODY = "{\"question\":\"Pourquoi ma facture change ?\",\"domain\":\"billing\"}";
    private static final String RETRIEVE_BODY = "{\"question\":\"Pourquoi ma facture change ?\",\"domain\":\"billing\"}";

    @Autowired
    private MockMvc mockMvc;

    @TestConfiguration
    static class Config {
        @Bean
        AnswerQuestionUseCase answerQuestionUseCase() {
            return (question, domain, topK, alreadyGreeted, history) ->
                    GeneratedAnswer.grounded("La proration explique l'écart.", 0.83);
        }

        @Bean
        GroundQueryUseCase groundQueryUseCase() {
            return (question, domain, topK, alreadyGreeted, language) -> {
                throw new AssertionError("use case must not run for an unauthorized request");
            };
        }

        @Bean
        LanguageDetector languageDetector() {
            return new LanguageDetector(AnswerLanguage.ENGLISH);
        }

        @Bean
        IngestKnowledgeUseCase ingestKnowledgeUseCase() {
            return new IngestKnowledgeUseCase() {
                @Override
                public int ingest(String content, String sourceName) {
                    throw new AssertionError("use case must not run for an unauthorized request");
                }

                @Override
                public int ingest(String content, String sourceName, String domain) {
                    throw new AssertionError("use case must not run for an unauthorized request");
                }
            };
        }

        @Bean
        SyncKnowledgeUseCase syncKnowledgeUseCase() {
            return new SyncKnowledgeUseCase() {
                @Override
                public com.voicesupport.knowledge.domain.model.valueobject.SyncReport syncAll() {
                    throw new AssertionError("use case must not run for an unauthorized request");
                }

                @Override
                public com.voicesupport.knowledge.domain.model.valueobject.SyncReport sync(String sourceType) {
                    throw new AssertionError("use case must not run for an unauthorized request");
                }
            };
        }
    }

    @Test
    @DisplayName("POST /answer without api-key is rejected with 401 + ErrorResponse")
    void answerRejectedWithoutKey() throws Exception {
        mockMvc.perform(post("/api/conversation/answer")
                        .contentType(MediaType.APPLICATION_JSON).content(ANSWER_BODY))
                .andExpect(status().isUnauthorized())
                .andExpect(jsonPath("$.error_code").value("ERR_401"));
    }

    @Test
    @DisplayName("POST /answer with a wrong api-key is rejected with 401")
    void answerRejectedWithWrongKey() throws Exception {
        mockMvc.perform(post("/api/conversation/answer")
                        .header("x-api-key", "nope")
                        .contentType(MediaType.APPLICATION_JSON).content(ANSWER_BODY))
                .andExpect(status().isUnauthorized());
    }

    @Test
    @DisplayName("POST /answer with the matching api-key is accepted with 200")
    void answerAcceptedWithKey() throws Exception {
        mockMvc.perform(post("/api/conversation/answer")
                        .header("x-api-key", "s3cret")
                        .contentType(MediaType.APPLICATION_JSON).content(ANSWER_BODY))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.text").value("La proration explique l'écart."));
    }

    @Test
    @DisplayName("POST /retrieve without api-key is rejected with 401")
    void retrieveRejectedWithoutKey() throws Exception {
        mockMvc.perform(post("/api/conversation/retrieve")
                        .contentType(MediaType.APPLICATION_JSON).content(RETRIEVE_BODY))
                .andExpect(status().isUnauthorized());
    }

    @Test
    @DisplayName("POST /knowledge/sync without api-key is rejected with 401")
    void syncAllRejectedWithoutKey() throws Exception {
        mockMvc.perform(post("/api/knowledge/sync"))
                .andExpect(status().isUnauthorized());
    }

    @Test
    @DisplayName("POST /knowledge/sync/{sourceType} without api-key is rejected with 401")
    void syncOneRejectedWithoutKey() throws Exception {
        mockMvc.perform(post("/api/knowledge/sync/markdown"))
                .andExpect(status().isUnauthorized());
    }

    @Test
    @DisplayName("POST /knowledge/ingest without api-key is rejected with 401")
    void ingestRejectedWithoutKey() throws Exception {
        MockMultipartFile file = new MockMultipartFile(
                "file", "kb.md", MediaType.TEXT_PLAIN_VALUE, "# doc".getBytes());
        mockMvc.perform(multipart("/api/knowledge/ingest").file(file))
                .andExpect(status().isUnauthorized());
    }
}
