package com.voicesupport.knowledge.domain.service;

import com.voicesupport.knowledge.domain.model.valueobject.SourceDocument;
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

        for (SourceDocument document : documents) {
            seenIds.add(document.sourceId());
            if (isUnchanged(document)) {
                skipped++;
            } else {
                totalChunks += reingest(document);
                ingested++;
            }
        }

        int deleted = removeStale(sourceType, seenIds);
        SyncReport report = new SyncReport(documents.size(), ingested, skipped, deleted);
        observer.syncCompleted(sourceType, report, totalChunks, elapsedMs(start));
        return report;
    }

    private boolean isUnchanged(SourceDocument document) {
        Optional<String> knownHash = statePort.findHash(document.sourceType(), document.sourceId());
        return knownHash.isPresent() && knownHash.get().equals(document.contentHash());
    }

    private int reingest(SourceDocument document) {
        vectorStorePort.deleteBySource(document.sourceType(), document.sourceId());
        List<TextChunker.Chunk> chunks = textChunker.chunk(document.content());
        long start = System.nanoTime();
        int stored = vectorStorePort.storeChunks(document, chunks);
        observer.batchStored(document.sourceType(), document.sourceId(), stored, elapsedMs(start));
        statePort.upsertState(
                document.sourceType(), document.sourceId(),
                document.contentHash(), document.updatedAt(), stored);
        return stored;
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
