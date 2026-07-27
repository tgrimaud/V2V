---
name: java-backend-developer
description: >-
  Develop Java backend applications with Spring Boot, following Clean Code, SOLID principles,
  and hexagonal architecture. Covers Spring-specific implementation patterns: REST controllers,
  DTOs, caching, WebClient adapters, bean registration by profile, JUnit 5 with manual fakes,
  and ArchUnit enforcement. Use when writing Java backend code, implementing ports/adapters,
  adding REST endpoints, configuring Spring beans, setting up caching, building output adapters
  for external APIs, or writing integration tests. For architectural principles and patterns,
  see also the software-architect skill.
---

# Java Backend Developer

Java/Spring implementation patterns for the hexagonal architecture described in the `software-architect` skill.

## Technology Stack

- **Java 17 LTS** with records, sealed classes, pattern matching (aligned with `pom.xml` and ADR-0026)
- **Spring Boot 3.x** with Spring Web, WebClient, Validation, Actuator, Cache
- **Maven** for build management
- **JUnit 5** with manual fake adapters (no Mockito)
- **ArchUnit** for architecture enforcement

## Architecture

This project follows **hexagonal architecture** with **DDD tactical patterns**. For the full architectural reference — package structure, layer rules, port/adapter boundaries, DDD patterns, the Hive modular monolith strategy, and ArchUnit enforcement — read the `software-architect` skill.

What follows are the **Java/Spring implementation patterns** for that architecture.

### Domain Services (Spring Wiring)

Domain services are pure Java — no Spring annotations. Register them via `@Bean` in infrastructure config:

```java
// domain/service/AnomalyDetectionService.java — pure business rules
public class AnomalyDetectionService {
    public List<Insight> analyzeTeamMembers(List<TeamMember> members) {
        // business logic operating on domain types only
    }
}

// infrastructure/config/DomainServiceConfig.java — wiring
@Configuration
public class DomainServiceConfig {
    @Bean
    public AnomalyDetectionService anomalyDetectionService() {
        return new AnomalyDetectionService();
    }
}
```

### Application Services

Spring `@Service` beans that orchestrate port calls, apply caching, and delegate to domain services:

```java
@Service
public class TeamService {
    private final TeamQueryPort teamQueryPort;

    public TeamService(TeamQueryPort teamQueryPort) {
        this.teamQueryPort = teamQueryPort;
    }

    @Cacheable("team")
    public List<TeamMember> getTeamMembers(DateRange range) {
        return teamQueryPort.getTeamMembers(range);
    }
}
```

## Java DDD Implementation

For the conceptual "when and why" of value objects, entities, ports, and domain exceptions, see the `software-architect` skill. Below are the Java-specific implementation patterns.

See `references/domain-modeling-patterns.md` for full examples (Money, AcceptanceRatio, UserId, Email, DateRange).

### Records as Value Objects and Entities

Use Java records with validation in the compact constructor:

```java
public record DateRange(LocalDate startDate, LocalDate endDate) {
    public DateRange {
        Objects.requireNonNull(startDate, "startDate required");
        Objects.requireNonNull(endDate, "endDate required");
        if (startDate.isAfter(endDate)) {
            throw new InvalidDateRangeException("start must be before end");
        }
        if (ChronoUnit.DAYS.between(startDate, endDate) > 30) {
            throw new InvalidDateRangeException("range cannot exceed 30 days");
        }
    }
}
```

### Domain Exceptions with Error Codes

```java
public class InvalidDateRangeException extends RuntimeException {
    private final String code;

    public InvalidDateRangeException(String message) {
        super(message);
        this.code = "ERR_002";
    }

    public String code() { return code; }
}
```

### Port Interfaces

```java
public interface TeamQueryPort {
    List<TeamMember> getTeamMembers(DateRange range);
    List<TeamMember> getTeamMembers(DateRange range, String teamId);
}
```

### Key Rules

**Money** — Use `Money` value object (`BigDecimal` + `Currency`), never `double` or bare `long`. Convert at adapter boundaries via `Money.ofCents(long)` or `Money.of(BigDecimal, Currency)`.

**Ratios** — Use `AcceptanceRatio(double value)` constrained to 0.0–1.0. Convert to `int` percentage only in DTOs.

**Typed IDs** — Wrap in records (`UserId`, `TeamId`). Unwrap to `String` via `.value()` only in DTOs.

**Email** — Validate format (regex) in the compact constructor.

## API Patterns

### Response Wrapper

```java
public record ApiResponse<T>(T data, Meta meta) {
    public record Meta(Instant timestamp, String requestId) {}

    public static <T> ApiResponse<T> of(T data, String requestId) {
        return new ApiResponse<>(data, new Meta(Instant.now(), requestId));
    }
}
```

### Error Response

```java
public record ErrorResponse(String code, String message, Instant timestamp) {
    public static ErrorResponse of(String code, String message) {
        return new ErrorResponse(code, message, Instant.now());
    }
}
```

### DTO Mapping

DTOs live in `infrastructure/adapter/in/rest/dto/` and use **static factory methods** rather than separate mapper classes.

```java
public record TeamMemberDto(
    String id, String name, String email,
    long totalRequests, long totalTokens, long spendCents,
    int acceptanceRatePercent, boolean active
) {
    public static TeamMemberDto fromDomain(TeamMember entity) {
        return new TeamMemberDto(
            entity.id().value(), entity.name(), entity.email().value(),
            entity.totalRequests(), entity.totalTokens(), entity.spend().toCents(),
            entity.acceptanceRatio().asPercentage(), entity.active()
        );
    }
}
```

### Global Exception Handler

```java
@RestControllerAdvice
public class GlobalExceptionHandler {

    @ExceptionHandler(InvalidDateRangeException.class)
    public ResponseEntity<ErrorResponse> handleInvalidDateRange(InvalidDateRangeException ex) {
        return ResponseEntity.badRequest()
            .body(ErrorResponse.of(ex.code(), ex.getMessage()));
    }

    @ExceptionHandler(MissingServletRequestParameterException.class)
    public ResponseEntity<ErrorResponse> handleMissingParam(MissingServletRequestParameterException ex) {
        return ResponseEntity.badRequest()
            .body(ErrorResponse.of("ERR_400", ex.getMessage()));
    }

    @ExceptionHandler(Exception.class)
    public ResponseEntity<ErrorResponse> handleGeneric(Exception ex) {
        log.error("Unhandled exception", ex);
        return ResponseEntity.internalServerError()
            .body(ErrorResponse.of("ERR_500", "Internal server error"));
    }
}
```

### JSON Conventions

Configure Jackson globally for `snake_case`:
```java
@Configuration
public class JacksonConfig {
    @Bean
    public Jackson2ObjectMapperBuilderCustomizer jsonCustomizer() {
        return builder -> builder
            .propertyNamingStrategy(PropertyNamingStrategies.SNAKE_CASE)
            .serializationInclusion(JsonInclude.Include.NON_NULL);
    }
}
```

## Caching

Spring Cache is used at the application service layer. Every `@Cacheable` cache name must be registered in `CacheConfig` or Spring will throw "Cannot find cache" at runtime.

```java
// infrastructure/config/CacheConfig.java
@Configuration
public class CacheConfig {
    @Bean
    public CacheManager cacheManager() {
        return new ConcurrentMapCacheManager(
            "analytics", "team", "userUsageDetail", "insights",
            "comparison", "teamComparison", "teams",
            "tokenSummary", "billingGroupMembers", "billingGroupEmails"
        );
    }
}
```

When adding a new `@Cacheable("newCacheName")`, always update `CacheConfig` to include the new name. Cache can be cleared via `POST /api/cache/clear` in dev/mock profiles.

## Output Adapters & WebClient

Output adapters live in `infrastructure/adapter/out/{system}/` (e.g., `cursor/` for the Cursor API). They implement output ports from `domain/port/out/`.

### WebClient Patterns

A shared `CursorApiClient` wraps WebClient and handles auth, retries, and timeouts centrally:

```java
public class CursorApiClient {
    private final WebClient adminClient;
    private static final Duration DEFAULT_TIMEOUT = Duration.ofSeconds(30);

    public <T> T adminGet(String path, Class<T> responseType) {
        return adminClient.get().uri(path)
            .retrieve()
            .bodyToMono(responseType)
            .retryWhen(rateLimitRetry())
            .timeout(DEFAULT_TIMEOUT)
            .block();
    }

    private Retry rateLimitRetry() {
        return Retry.fixedDelay(3, Duration.ofSeconds(5))
            .filter(ex -> ex instanceof WebClientResponseException wce
                && wce.getStatusCode().value() == 429);
    }
}
```

**Key patterns:**
- Centralize HTTP calls in a shared client, not in individual adapters
- Retry only on rate-limit (429), not on all errors
- Use `.block()` for synchronous calls from adapters
- For paginated endpoints that hit rate limits, add a delay between pages (e.g., 150ms `Thread.sleep`)
- Adapters catch exceptions from the client and log/wrap as needed

### Bean Registration by Profile

```java
// infrastructure/config/CursorApiConfig.java
@Configuration
@Profile("prod")
public class CursorApiConfig {
    @Bean
    public TeamQueryPort cursorApiTeamAdapter(CursorApiClient client,
                                              BillingGroupResolver resolver) {
        return new CursorApiTeamAdapter(client, resolver);
    }
}

// infrastructure/config/AdapterConfig.java
@Configuration
@Profile("!prod")
public class AdapterConfig {
    @Bean
    public TeamQueryPort mockTeamAdapter(MockDataGenerator gen) {
        return new MockTeamAdapter(gen);
    }
}
```

## Clean Code Rules

### Boy Scout Rule

Leave the code cleaner than you found it — bring the code you touch up to the current standard, behaviour-preserving. The canonical rule (scope to what you touch, test-before/after, keeping the cleanup as its own commit, and respecting mandatory constraints like interface-override method names) lives in the language-agnostic **code-guidelines** skill under *Refactoring Safety → "Leave it cleaner than you found it — the Boy Scout Rule"*. Follow it for Java too.

### Naming
- Classes: `PascalCase` (nouns)
- Methods: `camelCase` (verbs)
- Constants: `SCREAMING_SNAKE_CASE`
- Packages: all lowercase

### Methods
- Max 20 lines preferred
- Single level of abstraction
- Max 3 parameters (use objects for more)

### Comments Policy
- Self-documenting names replace comments
- Extract methods over adding comments
- No Javadoc on classes, interfaces, or methods
- Only comment WHY (non-obvious decisions), never WHAT

## Testing

### Integration Tests

Use `@SpringBootTest` with `@ActiveProfiles("mock")` for full-stack REST tests:

```java
@SpringBootTest
@AutoConfigureMockMvc
@ActiveProfiles("mock")
@DisplayName("Team API")
class TeamControllerIntegrationTest {

    @Autowired
    MockMvc mvc;

    @Test
    @DisplayName("GET /api/team/members returns 200 with member list")
    void getMembers_returnsData() throws Exception {
        mvc.perform(get("/api/team/members")
                .accept(MediaType.APPLICATION_JSON))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.data").isArray())
            .andExpect(jsonPath("$.data").isNotEmpty());
    }
}
```

For slice tests of a single controller (e.g., health checks), use `@WebMvcTest` with `@Import` of test configuration that provides fake beans.

### Unit Tests with Fakes

```java
class FakeAnalyticsAdapter implements AnalyticsQueryPort {
    private List<DailyActiveUsers> data = new ArrayList<>();

    public void setData(List<DailyActiveUsers> data) {
        this.data = data;
    }

    @Override
    public List<DailyActiveUsers> getDailyActiveUsers(DateRange range) {
        return data.stream()
            .filter(d -> !d.date().isBefore(range.startDate()))
            .filter(d -> !d.date().isAfter(range.endDate()))
            .toList();
    }
}
```

### ArchUnit Tests

See the `software-architect` skill's `references/archunit-tests.md` for complete examples. Key rules enforced:

- Domain layer has no Spring or infrastructure dependencies
- Ports are interfaces
- No field injection (`@Autowired` on fields)
- Controllers end with `Controller`, adapters end with `Adapter`

### Mutation Testing (PIT)

For *why* and *when* to use mutation testing, and how to read the result, see the `test-guidelines` skill's "Mutation Testing" section. This is the Java/Maven wiring.

Use **PIT** (`pitest-maven` + `pitest-junit5-plugin`) behind a dedicated `pitest` profile so the normal `mvn test` loop stays fast. Scope `targetClasses` / `targetTests` to the high-value deterministic domain (guardrails, thresholds, classifiers, money) — not the whole app.

```xml
<profile>
  <id>pitest</id>
  <build><plugins>
    <plugin>
      <groupId>org.pitest</groupId>
      <artifactId>pitest-maven</artifactId>
      <version>1.19.1</version>
      <dependencies>
        <dependency>
          <groupId>org.pitest</groupId>
          <artifactId>pitest-junit5-plugin</artifactId>
          <version>1.2.2</version>
        </dependency>
      </dependencies>
      <configuration>
        <targetClasses><param>com.example.domain.service.*</param></targetClasses>
        <targetTests><param>com.example.domain.service.*</param></targetTests>
        <outputFormats><param>HTML</param><param>XML</param></outputFormats>
        <timestampedReports>false</timestampedReports>
        <mutationThreshold>85</mutationThreshold> <!-- below baseline; ratchet up -->
      </configuration>
    </plugin>
  </plugins></build>
</profile>
```

**Gotcha — recompile first.** Invoking the goal alone runs against a *stale* `target/test-classes`, so new/edited tests are silently ignored and the score looks unchanged. Always drive it through a phase:

```bash
mvn -Ppitest test-compile org.pitest:pitest-maven:mutationCoverage
# report: target/pit-reports/index.html
```

**JDK note.** The build targets Java 17, which modern PIT (1.19.x) + junit5-plugin (1.2.x) fully support. PIT executes under the JVM that runs Maven; on a much newer runtime JDK it needs a PIT version recent enough for that bytecode (ASM major version) — PIT 1.19.1 runs fine under JDK 25. If a mutation run fails on an "unsupported class file major version", point `JAVA_HOME` at a JDK 17 for the PIT run.

### Test Structure

```
src/test/java/com/cursor/dashboard/
├── architecture/              # ArchUnit tests
├── domain/model/valueobject/  # Value object unit tests
├── infrastructure/adapter/in/rest/  # Integration tests
└── fake/                      # Fake adapters for testing
```

## Checklist

Before committing:

- [ ] Domain layer has no infrastructure dependencies
- [ ] Domain services registered via `@Bean` in `DomainServiceConfig` (no `@Service` in domain)
- [ ] Value objects are immutable records with validation
- [ ] Money uses `Money` value object (`BigDecimal` + `Currency`), never `double` or bare `long`
- [ ] Ratios use a value object (e.g., `AcceptanceRatio`), not raw `double` or `int`
- [ ] IDs use typed wrappers (`UserId`, `TeamId`), not raw `String`
- [ ] Ports are interfaces in `domain/port/out/` or `domain/port/in/`
- [ ] Adapters implement ports via constructor injection
- [ ] ArchUnit tests pass
- [ ] No Mockito — only manual fakes
- [ ] API responses use `ApiResponse<T>` wrapper
- [ ] Errors use `ErrorResponse` with codes
- [ ] JSON fields are `snake_case` (Jackson global config)
- [ ] Methods under 20 lines
- [ ] No Javadoc, no explanatory comments
- [ ] New `@Cacheable` names added to `CacheConfig`
- [ ] New `@RequestParam` names match frontend query params (snake_case)
