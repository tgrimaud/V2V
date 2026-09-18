package com.voicesupport.knowledge.domain.service;

import com.voicesupport.knowledge.domain.model.valueobject.SourceDocument;
import com.voicesupport.knowledge.domain.model.valueobject.StoreResult;
import com.voicesupport.knowledge.domain.model.valueobject.SyncReport;
import com.voicesupport.knowledge.domain.port.in.SyncKnowledgeUseCase;
import com.voicesupport.knowledge.domain.port.out.KnowledgeSourceConnector;
import com.voicesupport.knowledge.domain.port.out.KnowledgeSourceStatePort;
import com.voicesupport.knowledge.domain.port.out.SyncObserverPort;
import com.voicesupport.knowledge.domain.port.out.VectorStorePort;

import java.util.HashSet;
import java.util.List;
import java.util.Optional;
import java.util.Set;

public class KnowledgeSyncService implements SyncKnowledgeUseCase {

    private final List<KnowledgeSourceConnector> connectors;
    private final KnowledgeSourceStatePort statePort;
    private final VectorStorePort vectorStorePort;
    private final TextChunker textChunker;
    private final SyncObserverPort observer;

    public KnowledgeSyncService(
            List<KnowledgeSourceConnector> connectors,
            KnowledgeSourceStatePort statePort,
            VectorStorePort vectorStorePort,
            TextChunker textChunker,
            SyncObserverPort observer) {
        this.connectors = connectors;
        this.statePort = statePort;
        this.vectorStorePort = vectorStorePort;
        this.textChunker = textChunker;
        this.observer = observer;
    }

    @Override
    public SyncReport syncAll() {
        SyncReport report = SyncReport.empty();
        for (KnowledgeSourceConnector connector : connectors) {
            report = report.plus(syncConnector(connector));
        }
        return report;
    }

    @Override
    public SyncReport sync(String sourceType) {
        return connectors.stream()
                .filter(c -> c.sourceType().equals(sourceType))
                .findFirst()
                .map(this::syncConnector)
                .orElseThrow(() -> new IllegalArgumentException("No connector for source type: " + sourceType));
    }

    private SyncReport syncConnector(KnowledgeSourceConnector connector) {
        String sourceType = connector.sourceType();
        long start = System.nanoTime();
        List<SourceDocument> documents = connector.fetchAll();
        Set<String> seenIds = new HashSet<>();
        int ingested = 0;
        int skipped = 0;
        int totalChunks = 0;

        try {
            for (SourceDocument document : documents) {
                seenIds.add(document.sourceId());
                if (isUnchanged(document)) {
                    skipped++;
                } else {
                    StoreResult result = reingest(document);
                    totalChunks += result.stored();
                    if (result.isComplete()) {
                        ingested++;
                    }
                }
            }
            int deleted = removeStale(sourceType, seenIds);
            SyncReport report = new SyncReport(documents.size(), ingested, skipped, deleted);
            observer.syncCompleted(sourceType, report, totalChunks, elapsedMs(start));
            return report;
        } catch (RuntimeException failure) {
            // Fail-fast is intentional (ADR-0030): committed documents are skipped on the next
            // idempotent run. Emit the failure so the aborted run is observable and resumable.
            observer.syncFailed(sourceType, ingested, totalChunks, elapsedMs(start), errorCode(failure));
            throw failure;
        }
    }

    private static String errorCode(RuntimeException failure) {
        return failure.getClass().getSimpleName();
    }

    private boolean isUnchanged(SourceDocument document) {
        Optional<String> knownHash = statePort.findHash(document.sourceType(), document.sourceId());
        return knownHash.isPresent() && knownHash.get().equals(document.contentHash());
    }

    private StoreResult reingest(SourceDocument document) {
        vectorStorePort.deleteBySource(document.sourceType(), document.sourceId());
        List<TextChunker.Chunk> chunks = textChunker.chunk(document.content());
        long start = System.nanoTime();
        StoreResult result = vectorStorePort.storeChunks(document, chunks);
        observer.batchStored(document.sourceType(), document.sourceId(), result.stored(), elapsedMs(start));
        if (result.isComplete()) {
            statePort.upsertState(
                    document.sourceType(), document.sourceId(),
                    document.contentHash(), document.updatedAt(), result.stored());
        } else {
            // BUG-022: a partial store (a sub-batch was skipped after an embedding timeout/error) is
            // NOT committed. deleteBySource already ran, so leaving the content_hash uncommitted makes
            // the next idempotent sync retry the whole document — instead of marking it done and
            // silently dropping the missing chunks from the RAG forever.
            observer.batchSkipped(document.sourceType(), document.sourceId(), result.skipped());
        }
        return result;
    }

    private static long elapsedMs(long startNanos) {
        return (System.nanoTime() - startNanos) / 1_000_000;
    }

    private int removeStale(String sourceType, Set<String> seenIds) {
        int deleted = 0;
        for (String sourceId : statePort.listSourceIds(sourceType)) {
            if (!seenIds.contains(sourceId)) {
                vectorStorePort.deleteBySource(sourceType, sourceId);
                statePort.deleteState(sourceType, sourceId);
                deleted++;
            }
        }
        return deleted;
    }
}
