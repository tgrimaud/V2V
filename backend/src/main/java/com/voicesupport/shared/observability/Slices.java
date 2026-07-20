package com.voicesupport.shared.observability;

// Canonical backend latency slices (TASK-BE-009), mapped onto the ADR-0018 voice-journey
// taxonomy (RAG / LLM). Used as the `slice` tag on the voice_support.slice timer and in the
// [TELEMETRY] structured logs so p50/p95/p99 can be reported per slice, channel and provider.
public final class Slices {

    public static final String BACKEND_REQUEST = "backend_request";
    public static final String RETRIEVAL = "retrieval";
    public static final String LLM_WORDING = "llm_wording";
    // Streaming first-token slices (TASK-BE-007): time-to-first-token from the LLM stream and
    // time-to-first-emitted-chunk from the backend, distinct from the full-completion slices
    // above so first-token latency (RF-021) is reported separately from total answer time.
    public static final String LLM_FIRST_TOKEN = "llm_first_token";
    public static final String BACKEND_FIRST_TOKEN = "backend_first_token";

    private Slices() {
    }
}
