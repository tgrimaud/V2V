package com.voicesupport.knowledge.infrastructure.adapter.in.rest;

import com.voicesupport.knowledge.domain.model.valueobject.SyncReport;
import com.voicesupport.knowledge.domain.port.in.IngestKnowledgeUseCase;
import com.voicesupport.knowledge.domain.port.in.SyncKnowledgeUseCase;
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
    private final SyncKnowledgeUseCase syncKnowledgeUseCase;

    public KnowledgeController(
            IngestKnowledgeUseCase ingestKnowledgeUseCase,
            SyncKnowledgeUseCase syncKnowledgeUseCase) {
        this.ingestKnowledgeUseCase = ingestKnowledgeUseCase;
        this.syncKnowledgeUseCase = syncKnowledgeUseCase;
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
        return ResponseEntity.ok(syncKnowledgeUseCase.syncAll());
    }

    @PostMapping("/sync/{sourceType}")
    public ResponseEntity<SyncReport> sync(@PathVariable("sourceType") String sourceType) {
        return ResponseEntity.ok(syncKnowledgeUseCase.sync(sourceType));
    }
}
