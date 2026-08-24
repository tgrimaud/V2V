package com.voicesupport.knowledge.infrastructure.adapter.out.health;

import org.springframework.boot.actuate.health.Health;
import org.springframework.boot.actuate.health.HealthIndicator;
import org.springframework.http.client.SimpleClientHttpRequestFactory;
import org.springframework.web.client.RestClient;

// BUG-014: contributes an embedding-hop indicator to the aggregated /actuator/health so a
// broken Ollama path (DNS/connect failure) turns the node DOWN and HAProxy drains it, instead
// of staying green while RAG is offline. The probe is a cheap GET /api/tags (DNS + TCP + Ollama
// liveness) — the exact failure surface BUG-014 describes — not a full embedding call. Gated ON
// only on the pilot backend tier (EMBEDDING_HEALTH_ENABLED); local/dev/memory runs keep it off.
public class OllamaEmbeddingHealthAdapter implements HealthIndicator {

    // Test seam: the actual HTTP probe is injected so unit tests exercise UP/DOWN without a live
    // Ollama. Any thrown exception means the hop is unreachable.
    @FunctionalInterface
    public interface Probe {
        void check() throws Exception;
    }

    private static final String HOP = "embedding/ollama";

    private final Probe probe;

    public OllamaEmbeddingHealthAdapter(Probe probe) {
        this.probe = probe;
    }

    public static OllamaEmbeddingHealthAdapter http(String baseUrl, long connectMs, long readMs) {
        SimpleClientHttpRequestFactory factory = new SimpleClientHttpRequestFactory();
        factory.setConnectTimeout((int) connectMs);
        factory.setReadTimeout((int) readMs);
        RestClient client = RestClient.builder().requestFactory(factory).build();
        String url = baseUrl + "/api/tags";
        return new OllamaEmbeddingHealthAdapter(() -> client.get().uri(url).retrieve().toBodilessEntity());
    }

    @Override
    public Health health() {
        try {
            probe.check();
            return Health.up().withDetail("hop", HOP).build();
        } catch (Exception e) {
            // Only the exception class name is exposed (e.g. ResourceAccessException) — never a
            // message that could carry host/path detail into the health payload.
            return Health.down().withDetail("hop", HOP)
                    .withDetail("error", e.getClass().getSimpleName()).build();
        }
    }
}
