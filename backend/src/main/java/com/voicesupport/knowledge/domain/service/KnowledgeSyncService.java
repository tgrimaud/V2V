package com.voicesupport.knowledge.domain.service;

import com.voicesupport.knowledge.domain.model.valueobject.SourceDocument;
import com.voicesupport.knowledge.domain.model.valueobject.SyncReport;
import com.voicesupport.knowledge.domain.port.in.SyncKnowledgeUseCase;
import com.voicesupport.knowledge.domain.port.out.KnowledgeSourceConnector;
import com.voicesupport.knowledge.domain.port.out.KnowledgeSourceStatePort;
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

    public KnowledgeSyncService(
            List<KnowledgeSourceConnector> connectors,
            KnowledgeSourceStatePort statePort,
            VectorStorePort vectorStorePort,
            TextChunker textChunker) {
        this.connectors = connectors;
        this.statePort = statePort;
        this.vectorStorePort = vectorStorePort;
        this.textChunker = textChunker;
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
        List<SourceDocument> documents = connector.fetchAll();
        Set<String> seenIds = new HashSet<>();
        int ingested = 0;
        int skipped = 0;

        for (SourceDocument document : documents) {
            seenIds.add(document.sourceId());
            if (isUnchanged(document)) {
                skipped++;
            } else {
                reingest(document);
                ingested++;
            }
        }

        int deleted = removeStale(sourceType, seenIds);
        return new SyncReport(documents.size(), ingested, skipped, deleted);
    }

    private boolean isUnchanged(SourceDocument document) {
        Optional<String> knownHash = statePort.findHash(document.sourceType(), document.sourceId());
        return knownHash.isPresent() && knownHash.get().equals(document.contentHash());
    }

    private void reingest(SourceDocument document) {
        vectorStorePort.deleteBySource(document.sourceType(), document.sourceId());
        List<TextChunker.Chunk> chunks = textChunker.chunk(document.content());
        int chunkIndex = 0;
        for (TextChunker.Chunk chunk : chunks) {
            vectorStorePort.storeChunk(document, chunk.content(), chunk.section(), chunkIndex++);
        }
        statePort.upsertState(
                document.sourceType(), document.sourceId(),
                document.contentHash(), document.updatedAt(), chunks.size());
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
