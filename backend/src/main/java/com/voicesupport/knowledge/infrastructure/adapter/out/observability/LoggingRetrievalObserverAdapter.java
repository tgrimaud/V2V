package com.voicesupport.knowledge.infrastructure.adapter.out.observability;

import com.voicesupport.knowledge.domain.port.out.RetrievalObserverPort;
import io.micrometer.core.instrument.DistributionSummary;
import io.micrometer.core.instrument.MeterRegistry;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;

// Turns the query-time MMR event (TASK-BE-028) into a Micrometer distribution
// (voice_support.retrieval_mmr_selected — chunks kept out of the over-fetched set) plus a
// [RETRIEVAL-MMR] structured log. The per-slice RETRIEVAL latency is already timed upstream
// (BackendTelemetry.time on the seam adapter); this records the diversity re-ranking's in/out
// counts so a change in over-fetch/lambda is observable. Per-turn detail is DEBUG (avoids one
// INFO line per turn); the count distribution is always exported for aggregation.
@Component
public class LoggingRetrievalObserverAdapter implements RetrievalObserverPort {

    private static final Logger log = LoggerFactory.getLogger(LoggingRetrievalObserverAdapter.class);
    private static final String SELECTED_SUMMARY = "voice_support.retrieval_mmr_selected";

    private final MeterRegistry registry;

    public LoggingRetrievalObserverAdapter(MeterRegistry registry) {
        this.registry = registry;
    }

    @Override
    public void mmrApplied(String domain, int fetchK, int candidateCount, int selectedCount, double lambda) {
        DistributionSummary.builder(SELECTED_SUMMARY)
                .register(registry)
                .record(selectedCount);
        log.debug("[RETRIEVAL-MMR] op=mmr domain={} fetch_k={} candidates={} selected={} lambda={}",
                domain == null ? "any" : domain, fetchK, candidateCount, selectedCount, lambda);
    }
}
