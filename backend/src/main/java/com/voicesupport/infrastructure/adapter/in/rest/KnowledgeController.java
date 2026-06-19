package com.voicesupport.infrastructure.adapter.in.rest;

import com.voicesupport.domain.port.in.IngestKnowledgeUseCase;
import org.springframework.http.ResponseEntity;
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

    public KnowledgeController(IngestKnowledgeUseCase ingestKnowledgeUseCase) {
        this.ingestKnowledgeUseCase = ingestKnowledgeUseCase;
    }

    @PostMapping("/ingest")
    public ResponseEntity<Map<String, Object>> ingest(
            @RequestParam("file") MultipartFile file,
            @RequestParam(value = "source", required = false) String source) throws IOException {

        String content = new String(file.getBytes(), StandardCharsets.UTF_8);
        String sourceName = source != null ? source : file.getOriginalFilename();

        int chunksCreated = ingestKnowledgeUseCase.ingest(content, sourceName);

        return ResponseEntity.ok(Map.of(
                "status", "ingested",
                "source", sourceName,
                "chunks_created", chunksCreated
        ));
    }
}
