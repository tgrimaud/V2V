package com.voicesupport.knowledge.fake;

import com.voicesupport.knowledge.domain.model.valueobject.SourceDocument;
import com.voicesupport.knowledge.domain.port.out.KnowledgeSourceConnector;

import java.util.List;

public class FakeKnowledgeSourceConnector implements KnowledgeSourceConnector {

    private final String sourceType;
    private List<SourceDocument> documents;

    public FakeKnowledgeSourceConnector(String sourceType, List<SourceDocument> documents) {
        this.sourceType = sourceType;
        this.documents = documents;
    }

    public void setDocuments(List<SourceDocument> documents) {
        this.documents = documents;
    }

    @Override
    public String sourceType() {
        return sourceType;
    }

    @Override
    public List<SourceDocument> fetchAll() {
        return documents;
    }
}
