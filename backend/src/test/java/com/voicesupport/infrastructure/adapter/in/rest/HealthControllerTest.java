package com.voicesupport.infrastructure.adapter.in.rest;

import org.junit.jupiter.api.Test;

import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertEquals;

class HealthControllerTest {

    @Test
    void health_returns_service_status() {
        // GIVEN
        HealthController controller = new HealthController();

        // WHEN
        Map<String, String> response = controller.health();

        // THEN
        assertEquals("up", response.get("status"));
        assertEquals("voice-support-bot", response.get("service"));
    }
}
