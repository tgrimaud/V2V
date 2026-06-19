# Spring Boot Project Setup Reference

## Spring Initializr Command

```bash
spring init \
  --build=maven \
  --java-version=21 \
  --dependencies=web,webflux,validation,actuator \
  --group-id=com.cursor \
  --artifact-id=dashboard \
  --name=cursor-dashboard \
  --package-name=com.cursor.dashboard \
  cursor-dashboard-backend
```

## Manual Setup via start.spring.io

1. Go to https://start.spring.io
2. Select:
   - **Project:** Maven
   - **Language:** Java
   - **Spring Boot:** 3.4.x
   - **Java:** 21
3. Add dependencies:
   - Spring Web
   - Spring WebFlux (for WebClient)
   - Validation
   - Spring Boot Actuator
4. Generate and extract

## Additional Dependencies (pom.xml)

```xml
<!-- ArchUnit for architecture tests -->
<dependency>
    <groupId>com.tngtech.archunit</groupId>
    <artifactId>archunit-junit5</artifactId>
    <version>1.2.1</version>
    <scope>test</scope>
</dependency>

<!-- OpenAPI/Swagger documentation -->
<dependency>
    <groupId>org.springdoc</groupId>
    <artifactId>springdoc-openapi-starter-webmvc-ui</artifactId>
    <version>2.3.0</version>
</dependency>

<!-- AssertJ for fluent assertions -->
<dependency>
    <groupId>org.assertj</groupId>
    <artifactId>assertj-core</artifactId>
    <scope>test</scope>
</dependency>
```

## Package Restructuring

After generating, restructure to hexagonal packages:

```bash
# Create hexagonal structure
mkdir -p src/main/java/com/cursor/dashboard/domain/model/{aggregate,entity,valueobject}
mkdir -p src/main/java/com/cursor/dashboard/domain/{service,exception,factory}
mkdir -p src/main/java/com/cursor/dashboard/domain/port/{out,in}
mkdir -p src/main/java/com/cursor/dashboard/application/service
mkdir -p src/main/java/com/cursor/dashboard/infrastructure/adapter/out/{mock,cursor}
mkdir -p src/main/java/com/cursor/dashboard/infrastructure/adapter/in/rest/dto
mkdir -p src/main/java/com/cursor/dashboard/infrastructure/config

# Create test structure
mkdir -p src/test/java/com/cursor/dashboard/architecture
mkdir -p src/test/java/com/cursor/dashboard/domain/model/valueobject
mkdir -p src/test/java/com/cursor/dashboard/domain/service
mkdir -p src/test/java/com/cursor/dashboard/application/service
mkdir -p src/test/java/com/cursor/dashboard/infrastructure/adapter/in/rest
mkdir -p src/test/java/com/cursor/dashboard/fake
```

## Configuration Files

### application.yml

```yaml
spring:
  application:
    name: cursor-dashboard

server:
  port: 8080

# OpenAPI
springdoc:
  api-docs:
    path: /api-docs
  swagger-ui:
    path: /swagger-ui.html

# Actuator
management:
  endpoints:
    web:
      exposure:
        include: health,info
```

### application-dev.yml

```yaml
spring:
  profiles:
    active: dev

logging:
  level:
    com.cursor.dashboard: DEBUG
    org.springframework.web: DEBUG

# CORS for frontend dev server
cors:
  allowed-origins: http://localhost:5173
```

### application-prod.yml

```yaml
spring:
  profiles:
    active: prod

logging:
  level:
    com.cursor.dashboard: INFO
    root: WARN
```

## Configuration Classes

### WebConfig.java

```java
@Configuration
public class WebConfig implements WebMvcConfigurer {

    @Value("${cors.allowed-origins:http://localhost:5173}")
    private String allowedOrigins;

    @Override
    public void addCorsMappings(CorsRegistry registry) {
        registry.addMapping("/api/**")
            .allowedOrigins(allowedOrigins.split(","))
            .allowedMethods("GET", "POST", "PUT", "DELETE", "OPTIONS")
            .allowedHeaders("*")
            .allowCredentials(true);
    }
}
```

### JacksonConfig.java

```java
@Configuration
public class JacksonConfig {

    @Bean
    public Jackson2ObjectMapperBuilderCustomizer jsonCustomizer() {
        return builder -> builder
            .propertyNamingStrategy(PropertyNamingStrategies.SNAKE_CASE)
            .serializationInclusion(JsonInclude.Include.NON_NULL)
            .featuresToDisable(SerializationFeature.WRITE_DATES_AS_TIMESTAMPS)
            .modules(new JavaTimeModule());
    }
}
```

### OpenApiConfig.java

```java
@Configuration
public class OpenApiConfig {

    @Bean
    public OpenAPI customOpenAPI() {
        return new OpenAPI()
            .info(new Info()
                .title("Cursor Dashboard API")
                .version("1.0")
                .description("Analytics dashboard for Cursor IDE usage"));
    }
}
```

### CacheConfig.java

```java
@Configuration
@EnableCaching
public class CacheConfig {

    @Bean
    public CacheManager cacheManager() {
        return new ConcurrentMapCacheManager("analytics", "team");
    }
}
```

### AdapterConfig.java

```java
@Configuration
public class AdapterConfig {

    @Bean
    @Profile("dev")
    public AnalyticsQueryPort mockAnalyticsAdapter() {
        return new MockAnalyticsAdapter();
    }

    @Bean
    @Profile("prod")
    public AnalyticsQueryPort cursorApiAdapter(WebClient.Builder webClientBuilder) {
        return new CursorApiAnalyticsAdapter(webClientBuilder);
    }
}
```

## Logging (logback-spring.xml)

```xml
<?xml version="1.0" encoding="UTF-8"?>
<configuration>
    <springProfile name="dev">
        <appender name="CONSOLE" class="ch.qos.logback.core.ConsoleAppender">
            <encoder>
                <pattern>%d{HH:mm:ss.SSS} [%thread] %-5level %logger{36} - %msg%n</pattern>
            </encoder>
        </appender>
        <root level="INFO">
            <appender-ref ref="CONSOLE"/>
        </root>
    </springProfile>

    <springProfile name="prod">
        <appender name="CONSOLE" class="ch.qos.logback.core.ConsoleAppender">
            <encoder class="net.logstash.logback.encoder.LogstashEncoder"/>
        </appender>
        <root level="INFO">
            <appender-ref ref="CONSOLE"/>
        </root>
    </springProfile>
</configuration>
```

## Running the Application

```bash
# Development
mvn spring-boot:run -Dspring-boot.run.profiles=dev

# Production
mvn spring-boot:run -Dspring-boot.run.profiles=prod

# Run tests
mvn test

# Run ArchUnit tests only
mvn test -Dtest=*ArchitectureTest
```
