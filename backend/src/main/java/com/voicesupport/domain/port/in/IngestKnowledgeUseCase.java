package com.voicesupport.domain.port.in;

public interface IngestKnowledgeUseCase {

    int ingest(String content, String sourceName);
}
