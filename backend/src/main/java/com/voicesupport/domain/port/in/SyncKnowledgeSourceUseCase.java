package com.voicesupport.domain.port.in;

import com.voicesupport.domain.model.SyncReport;

public interface SyncKnowledgeSourceUseCase {

    SyncReport syncAll();

    SyncReport sync(String sourceType);
}
