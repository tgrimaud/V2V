package com.voicesupport.conversation.infrastructure.adapter.in.rest;

import com.voicesupport.conversation.domain.model.valueobject.WarmUpResult;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.http.ResponseEntity;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

@DisplayName("WarmUpController (POST /api/conversation/warm-up)")
class WarmUpControllerTest {

    @Test
    @DisplayName("returns 200 with the per-model warm-up outcome on a full warm-up")
    void returns_full_warmup_outcome() {
        // GIVEN a use case that reports both models warmed
        WarmUpController controller = new WarmUpController(() -> new WarmUpResult(true, true, 42));

        // WHEN the endpoint is called
        ResponseEntity<WarmUpResponse> response = controller.warmUp();

        // THEN it is a 200 carrying the flags and duration
        assertEquals(200, response.getStatusCode().value());
        WarmUpResponse body = response.getBody();
        assertTrue(body.embeddingWarmed());
        assertTrue(body.llmWarmed());
        assertTrue(body.fullyWarmed());
        assertEquals(42, body.durationMs());
    }

    @Test
    @DisplayName("still returns 200 when a warm-up misses, with fully_warmed false (best-effort)")
    void returns_partial_warmup_outcome() {
        // GIVEN a use case where the LLM warm-up missed
        WarmUpController controller = new WarmUpController(() -> new WarmUpResult(true, false, 10));

        // WHEN the endpoint is called
        ResponseEntity<WarmUpResponse> response = controller.warmUp();

        // THEN it is still a 200 and fully_warmed is false
        assertEquals(200, response.getStatusCode().value());
        WarmUpResponse body = response.getBody();
        assertTrue(body.embeddingWarmed());
        assertFalse(body.llmWarmed());
        assertFalse(body.fullyWarmed());
    }
}
