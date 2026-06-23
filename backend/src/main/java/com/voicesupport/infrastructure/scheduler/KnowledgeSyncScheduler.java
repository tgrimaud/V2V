package com.voicesupport.infrastructure.scheduler;

import com.voicesupport.domain.model.SyncReport;
import com.voicesupport.domain.port.in.SyncKnowledgeSourceUseCase;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.scheduling.annotation.Scheduled;

public class KnowledgeSyncScheduler {

    private static final Logger log = LoggerFactory.getLogger(KnowledgeSyncScheduler.class);

    private final SyncKnowledgeSourceUseCase syncUseCase;

    public KnowledgeSyncScheduler(SyncKnowledgeSourceUseCase syncUseCase) {
        this.syncUseCase = syncUseCase;
    }

    @Scheduled(cron = "${voice-support.knowledge.sync-cron:0 0 * * * *}")
    public void scheduledSync() {
        try {
            SyncReport report = syncUseCase.syncAll();
            log.info("[KB-SYNC] scheduled sync done: {}", report);
        } catch (RuntimeException e) {
            log.error("[KB-SYNC] scheduled sync failed: {}", e.getMessage(), e);
        }
    }
}
