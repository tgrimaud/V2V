package com.voicesupport.infrastructure.adapter.in.rest;

import com.voicesupport.domain.model.SyncReport;
import com.voicesupport.domain.port.in.IngestKnowledgeUseCase;
import com.voicesupport.domain.port.in.SyncKnowledgeSourceUseCase;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.multipart.MultipartFile;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.util.Map;

@RestController
@RequestMapping("/api/knowledge")
public class KnowledgeController {

    private final IngestKnowledgeUseCase ingestKnowledgeUseCase;
    private final SyncKnowledgeSourceUseCase syncKnowledgeSourceUseCase;

    public KnowledgeController(
            IngestKnowledgeUseCase ingestKnowledgeUseCase,
            SyncKnowledgeSourceUseCase syncKnowledgeSourceUseCase) {
        this.ingestKnowledgeUseCase = ingestKnowledgeUseCase;
        this.syncKnowledgeSourceUseCase = syncKnowledgeSourceUseCase;
    }

    @PostMapping("/ingest")
    public ResponseEntity<Map<String, Object>> ingest(
            @RequestParam("file") MultipartFile file,
            @RequestParam(value = "source", required = false) String source,
            @RequestParam(value = "domain", required = false) String domain) throws IOException {

        String content = new String(file.getBytes(), StandardCharsets.UTF_8);
        String sourceName = source != null ? source : file.getOriginalFilename();

        int chunksCreated = ingestKnowledgeUseCase.ingest(content, sourceName, domain);

        return ResponseEntity.ok(Map.of(
                "status", "ingested",
                "source", sourceName,
                "domain", domain != null ? domain : "general",
                "chunks_created", chunksCreated
        ));
    }

    @PostMapping("/sync")
    public ResponseEntity<SyncReport> syncAll() {
        return ResponseEntity.ok(syncKnowledgeSourceUseCase.syncAll());
    }

    @PostMapping("/sync/{sourceType}")
    public ResponseEntity<SyncReport> sync(@PathVariable("sourceType") String sourceType) {
        return ResponseEntity.ok(syncKnowledgeSourceUseCase.sync(sourceType));
    }
}
