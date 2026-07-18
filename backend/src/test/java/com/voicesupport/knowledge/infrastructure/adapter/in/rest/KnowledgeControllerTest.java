package com.voicesupport.knowledge.infrastructure.adapter.in.rest;

import com.voicesupport.knowledge.domain.model.valueobject.SyncReport;
import com.voicesupport.knowledge.domain.port.in.IngestKnowledgeUseCase;
import com.voicesupport.knowledge.domain.port.in.SyncKnowledgeUseCase;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.mock.web.MockMultipartFile;
import org.springframework.test.web.servlet.MockMvc;

import java.nio.charset.StandardCharsets;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.multipart;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(KnowledgeController.class)
@DisplayName("Knowledge API")
class KnowledgeControllerTest {

    @Autowired
    MockMvc mvc;

    @TestConfiguration
    static class Fakes {

        @Bean
        SyncKnowledgeUseCase syncKnowledgeUseCase() {
            return new SyncKnowledgeUseCase() {
                @Override
                public SyncReport syncAll() {
                    return new SyncReport(3, 3, 0, 0);
                }

                @Override
                public SyncReport sync(String sourceType) {
                    return new SyncReport(3, 0, 3, 0);
                }
            };
        }

        @Bean
        IngestKnowledgeUseCase ingestKnowledgeUseCase() {
            return new IngestKnowledgeUseCase() {
                @Override
                public int ingest(String content, String sourceName) {
                    return ingest(content, sourceName, null);
                }

                @Override
                public int ingest(String content, String sourceName, String domain) {
                    return 2;
                }
            };
        }
    }

    @Test
    @DisplayName("POST /api/knowledge/sync returns the sync report")
    void syncAll_returnsReport() throws Exception {
        mvc.perform(post("/api/knowledge/sync"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.processed").value(3))
                .andExpect(jsonPath("$.ingested").value(3))
                .andExpect(jsonPath("$.skipped").value(0))
                .andExpect(jsonPath("$.deleted").value(0));
    }

    @Test
    @DisplayName("POST /api/knowledge/sync/{sourceType} returns the per-type report")
    void syncByType_returnsReport() throws Exception {
        mvc.perform(post("/api/knowledge/sync/markdown"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.processed").value(3))
                .andExpect(jsonPath("$.skipped").value(3));
    }

    @Test
    @DisplayName("POST /api/knowledge/ingest stores the file and echoes source, domain, chunk count")
    void ingest_returnsIngestedStatus() throws Exception {
        MockMultipartFile file = new MockMultipartFile(
                "file", "manual.md", "text/markdown",
                "# Manual\n\nBody.".getBytes(StandardCharsets.UTF_8));

        mvc.perform(multipart("/api/knowledge/ingest").file(file).param("domain", "billing"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.status").value("ingested"))
                .andExpect(jsonPath("$.source").value("manual.md"))
                .andExpect(jsonPath("$.domain").value("billing"))
                .andExpect(jsonPath("$.chunks_created").value(2));
    }
}
