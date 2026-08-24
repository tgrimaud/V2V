package com.voicesupport.conversation.infrastructure.actuator;

import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.boot.actuate.autoconfigure.data.redis.RedisHealthContributorAutoConfiguration;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.autoconfigure.data.redis.RedisAutoConfiguration;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;

import static org.assertj.core.api.Assertions.assertThat;

// TASK-BE-021 adversarial-review blocking fix: adding spring-boot-starter-data-redis auto-registers a
// Redis health indicator that is aggregated into /actuator/health. In the default `memory` store mode
// Redis is not deployed, so an un-gated indicator would ping localhost:6379 and flip /actuator/health
// to DOWN — marking the container unhealthy (image HEALTHCHECK + HAProxy) though the backend is fine.
// application.yml sets management.health.redis.enabled=${REDIS_HEALTH_ENABLED:false}. These tests pin
// that the gate actually adds/removes the Redis health contributor, without a live Redis.
@DisplayName("Redis actuator health indicator is gated by management.health.redis.enabled (TASK-BE-021)")
class RedisHealthIndicatorGateTest {

    private final ApplicationContextRunner runner = new ApplicationContextRunner()
            .withConfiguration(AutoConfigurations.of(
                    RedisAutoConfiguration.class,
                    RedisHealthContributorAutoConfiguration.class));

    @Test
    @DisplayName("memory mode (default false): redis health contributor is NOT registered → /actuator/health cannot flip DOWN on absent Redis")
    void disabledByDefaultKeepsHealthGreenWithoutRedis() {
        runner.withPropertyValues("management.health.redis.enabled=false")
                .run(context -> assertThat(context).doesNotHaveBean("redisHealthContributor"));
    }

    @Test
    @DisplayName("redis mode (REDIS_HEALTH_ENABLED=true): redis health contributor IS registered so Redis is monitored")
    void enabledWhenRequestedRegistersContributor() {
        runner.withPropertyValues("management.health.redis.enabled=true")
                .run(context -> assertThat(context).hasBean("redisHealthContributor"));
    }
}
