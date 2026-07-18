package com.voicesupport.knowledge.domain.port.in;

import com.voicesupport.knowledge.domain.model.valueobject.SyncReport;

public interface SyncKnowledgeUseCase {

    SyncReport syncAll();

    SyncReport sync(String sourceType);
}
