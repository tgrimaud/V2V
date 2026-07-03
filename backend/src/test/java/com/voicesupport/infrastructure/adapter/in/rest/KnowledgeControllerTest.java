package com.voicesupport.infrastructure.adapter.in.rest;

import com.voicesupport.domain.model.SyncReport;
import com.voicesupport.domain.port.in.IngestKnowledgeUseCase;
import com.voicesupport.domain.port.in.SyncKnowledgeSourceUseCase;
import org.junit.jupiter.api.Test;
import org.springframework.mock.web.MockMultipartFile;

import java.io.IOException;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertEquals;

class KnowledgeControllerTest {

    @Test
    void ingest_uses_filename_and_general_domain_when_optional_params_are_missing() throws IOException {
        // GIVEN
        RecordingIngestUseCase ingestUseCase = new RecordingIngestUseCase();
        KnowledgeController controller = new KnowledgeController(ingestUseCase, new RecordingSyncUseCase());
        MockMultipartFile file = new MockMultipartFile("file", "faq.md", "text/markdown", "hello".getBytes());

        // WHEN
        Map<String, Object> response = controller.ingest(file, null, null).getBody();

        // THEN
        assertEquals("faq.md", ingestUseCase.sourceName);
        assertEquals("general", response.get("domain"));
        assertEquals(2, response.get("chunks_created"));
    }

    @Test
    void sync_delegates_to_selected_source() {
        // GIVEN
        RecordingSyncUseCase syncUseCase = new RecordingSyncUseCase();
        KnowledgeController controller = new KnowledgeController(new RecordingIngestUseCase(), syncUseCase);

        // WHEN
        SyncReport response = controller.sync("markdown").getBody();

        // THEN
        assertEquals("markdown", syncUseCase.sourceType);
        assertEquals(1, response.processed());
    }

    static class RecordingIngestUseCase implements IngestKnowledgeUseCase {
        String sourceName;

        @Override
        public int ingest(String content, String sourceName) {
            return ingest(content, sourceName, "general");
        }

        @Override
        public int ingest(String content, String sourceName, String domain) {
            this.sourceName = sourceName;
            return 2;
        }
    }

    static class RecordingSyncUseCase implements SyncKnowledgeSourceUseCase {
        String sourceType;

        @Override
        public SyncReport syncAll() {
            return new SyncReport(3, 2, 1, 0);
        }

        @Override
        public SyncReport sync(String sourceType) {
            this.sourceType = sourceType;
            return new SyncReport(1, 1, 0, 0);
        }
    }
}
