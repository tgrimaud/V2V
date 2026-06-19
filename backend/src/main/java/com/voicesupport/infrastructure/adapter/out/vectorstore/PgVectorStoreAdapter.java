package com.voicesupport.infrastructure.adapter.out.vectorstore;

import com.voicesupport.domain.model.Citation;
import com.voicesupport.domain.port.out.VectorSearchPort;
import com.voicesupport.domain.port.out.VectorStorePort;
import org.springframework.ai.document.Document;
import org.springframework.ai.vectorstore.SearchRequest;
import org.springframework.ai.vectorstore.VectorStore;

import java.util.List;
import java.util.Map;

public class PgVectorStoreAdapter implements VectorStorePort, VectorSearchPort {

    private final VectorStore vectorStore;

    public PgVectorStoreAdapter(VectorStore vectorStore) {
        this.vectorStore = vectorStore;
    }

    @Override
    public void store(String content, String source, String section, int chunkIndex) {
        Document document = new Document(content, Map.of(
                "source", source,
                "section", section,
                "chunk_index", String.valueOf(chunkIndex)
        ));
        vectorStore.add(List.of(document));
    }

    @Override
    public List<Citation> searchRelevant(String query, int topK) {
        List<Document> results = vectorStore.similaritySearch(
                SearchRequest.builder()
                        .query(query)
                        .topK(topK)
                        .similarityThreshold(0.5)
                        .build()
        );

        return results.stream()
                .map(doc -> new Citation(
                        getMetadata(doc, "source"),
                        getMetadata(doc, "section"),
                        doc.getText(),
                        doc.getScore() != null ? doc.getScore() : 0.0
                ))
                .toList();
    }

    private String getMetadata(Document doc, String key) {
        Object value = doc.getMetadata().get(key);
        return value != null ? value.toString() : "unknown";
    }
}
