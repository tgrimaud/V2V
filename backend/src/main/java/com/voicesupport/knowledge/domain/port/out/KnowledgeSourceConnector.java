package com.voicesupport.knowledge.domain.port.out;

import com.voicesupport.knowledge.domain.model.valueobject.SourceDocument;
import java.util.List;

public interface KnowledgeSourceConnector {

    String sourceType();

    List<SourceDocument> fetchAll();
}
