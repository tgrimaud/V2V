package com.voicesupport.knowledge.domain.port.in;

public interface IngestKnowledgeUseCase {

    int ingest(String content, String sourceName);

    int ingest(String content, String sourceName, String domain);
}
