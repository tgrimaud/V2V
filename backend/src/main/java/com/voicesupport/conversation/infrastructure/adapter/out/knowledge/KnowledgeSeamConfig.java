package com.voicesupport.conversation.infrastructure.adapter.out.knowledge;

import com.voicesupport.conversation.domain.port.out.KnowledgeRetrievalPort;
import com.voicesupport.knowledge.domain.port.in.KnowledgeRetrievalUseCase;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

// Wiring for the outbound seam lives inside the seam package: it is the only place
// allowed to reference the knowledge context's published API (ADR-0027 boundary,
// enforced by ContextBoundaryTest).
@Configuration
public class KnowledgeSeamConfig {

    @Bean
    public KnowledgeRetrievalPort knowledgeRetrievalPort(KnowledgeRetrievalUseCase knowledgeRetrievalUseCase) {
        return new InProcKnowledgeRetrievalAdapter(knowledgeRetrievalUseCase);
    }
}
