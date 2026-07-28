package com.voicesupport.knowledge.infrastructure.adapter.in.rest;

import com.voicesupport.knowledge.domain.model.valueobject.SyncReport;
import com.voicesupport.knowledge.domain.port.in.IngestKnowledgeUseCase;
import com.voicesupport.knowledge.domain.port.in.SyncKnowledgeUseCase;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.Parameter;
import io.swagger.v3.oas.annotations.tags.Tag;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.MediaType;
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
import java.util.function.Supplier;

@RestController
@RequestMapping("/api/knowledge")
@Tag(name = "Knowledge base", description = "Ingest and synchronize knowledge-base sources into the vector store.")
public class KnowledgeController {

    private static final Logger log = LoggerFactory.getLogger(KnowledgeController.class);

    private final IngestKnowledgeUseCase ingestKnowledgeUseCase;
    private final SyncKnowledgeUseCase syncKnowledgeUseCase;

    public KnowledgeController(
            IngestKnowledgeUseCase ingestKnowledgeUseCase,
            SyncKnowledgeUseCase syncKnowledgeUseCase) {
        this.ingestKnowledgeUseCase = ingestKnowledgeUseCase;
        this.syncKnowledgeUseCase = syncKnowledgeUseCase;
    }

    @PostMapping(value = "/ingest", consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
    @Operation(summary = "One-shot document upload",
            description = "Chunks and embeds an uploaded UTF-8 text/markdown file into the vector store. "
                    + "Returns {status, source, domain, chunks_created}.")
    public ResponseEntity<Map<String, Object>> ingest(
            @RequestParam("file") MultipartFile file,
            @Parameter(description = "Logical source name; defaults to the uploaded file name.")
            @RequestParam(value = "source", required = false) String source,
            @Parameter(description = "Domain tag (billing|support|commercial); defaults to general.")
            @RequestParam(value = "domain", required = false) String domain) throws IOException {

        String content = new String(file.getBytes(), StandardCharsets.UTF_8);
        String sourceName = source != null ? source : file.getOriginalFilename();
        long start = System.nanoTime();
        int chunksCreated = ingestKnowledgeUseCase.ingest(content, sourceName, domain);
        log.info("[KB-SYNC] op=ingest source={} domain={} chunks_created={} duration_ms={}",
                sourceName, domain != null ? domain : "general", chunksCreated, elapsedMs(start));

        return ResponseEntity.ok(Map.of(
                "status", "ingested",
                "source", sourceName,
                "domain", domain != null ? domain : "general",
                "chunks_created", chunksCreated
        ));
    }

    @PostMapping("/sync")
    @Operation(summary = "Sync all connectors",
            description = "Idempotently syncs every configured knowledge source (skip on unchanged "
                    + "content hash, upsert otherwise, delete-diff via the ledger).")
    public ResponseEntity<SyncReport> syncAll() {
        return ResponseEntity.ok(timedSync("syncAll", "all", syncKnowledgeUseCase::syncAll));
    }

    @PostMapping("/sync/{sourceType}")
    @Operation(summary = "Sync one connector",
            description = "Idempotently syncs a single source type (e.g. markdown, csv).")
    public ResponseEntity<SyncReport> sync(
            @Parameter(description = "Connector source type to sync, e.g. markdown or csv.")
            @PathVariable("sourceType") String sourceType) {
        return ResponseEntity.ok(timedSync("sync", sourceType, () -> syncKnowledgeUseCase.sync(sourceType)));
    }

    private SyncReport timedSync(String op, String sourceType, Supplier<SyncReport> action) {
        long start = System.nanoTime();
        SyncReport report = action.get();
        log.info("[KB-SYNC] op={} source_type={} processed={} ingested={} skipped={} deleted={} duration_ms={}",
                op, sourceType, report.processed(), report.ingested(), report.skipped(),
                report.deleted(), elapsedMs(start));
        return report;
    }

    private static long elapsedMs(long startNanos) {
        return (System.nanoTime() - startNanos) / 1_000_000;
    }
}
