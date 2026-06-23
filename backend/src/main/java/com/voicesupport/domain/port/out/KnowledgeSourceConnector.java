package com.voicesupport.domain.port.out;

import com.voicesupport.domain.model.SourceDocument;

import java.util.List;

public interface KnowledgeSourceConnector {

    String sourceType();

    List<SourceDocument> fetchAll();
}
