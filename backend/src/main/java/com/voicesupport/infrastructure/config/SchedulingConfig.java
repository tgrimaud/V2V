package com.voicesupport.infrastructure.config;

import com.voicesupport.domain.port.in.SyncKnowledgeSourceUseCase;
import com.voicesupport.infrastructure.scheduler.KnowledgeSyncScheduler;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.EnableScheduling;

@Configuration
@EnableScheduling
public class SchedulingConfig {

    @Bean
    public KnowledgeSyncScheduler knowledgeSyncScheduler(SyncKnowledgeSourceUseCase syncUseCase) {
        return new KnowledgeSyncScheduler(syncUseCase);
    }
}
