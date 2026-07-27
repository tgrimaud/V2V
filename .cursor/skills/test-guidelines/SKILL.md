---
name: test-guidelines
description: >-
  Enforce team test writing standards (GIVEN/WHEN/THEN, naming, mocking, assertions).
  Use when writing, reviewing, or generating unit tests, integration tests, component tests,
  E2E tests, or test classes. Triggers on: "write a test", "add tests", "test for",
  "review this test", "test guidelines", "testing best practices", "naming convention for tests",
  "how to mock", "snapshot test", "test coverage". Applies to Java/JUnit/Spring backend
  and React/TypeScript/Vitest/Jest frontend tests.
---

# Test Guidelines

Standards for writing clear, maintainable, and trustworthy tests across backend and frontend code.

## Why These Rules Exist

Tests are documentation. A well-written test tells a future developer exactly what the code is supposed to do — and catches regressions before they ship. These guidelines keep tests readable, independent, and honest. When tests are sloppy, developers lose trust in them and stop running them. When tests are over-mocked, they give false confidence. These rules strike the balance.

---

## Test Structure and Readability

### GIVEN / WHEN / THEN (mandatory)

Every test follows the GIVEN-WHEN-THEN pattern with explicit comments. Exactly one of each, in this order. This makes intent scannable in seconds.

**Exception:** For tests that assert an exception is thrown, `// WHEN` and `// THEN` may be combined as `// WHEN / THEN` since `assertThatThrownBy` or `assertThrows` wraps both the action and the assertion. Similarly, for simple component renders with no setup, `// GIVEN` and `// WHEN` may be combined as `// GIVEN / WHEN`.

```java
@Test
void get_user_by_id_returns_user_when_exists() {
    // GIVEN
    var userId = new UserId("user-1");
    repository.save(new User(userId, "Alice"));

    // WHEN
    var result = service.getUserById(userId);

    // THEN
    assertThat(result).isPresent();
    assertThat(result.get().name()).isEqualTo("Alice");
}

@Test
void create_order_throws_when_cart_is_empty() {
    // GIVEN
    var emptyCart = new Cart(List.of());

    // WHEN / THEN
    assertThatThrownBy(() -> service.createOrder(emptyCart))
        .isInstanceOf(EmptyCartException.class);
}
```

```typescript
it('displays_error_message_when_fetch_fails', () => {
  // GIVEN
  server.use(http.get('/api/data', () => HttpResponse.error()));

  // WHEN
  render(<DataPanel />);

  // THEN
  expect(screen.getByRole('alert')).toHaveTextContent(/failed/i);
});
```

### Keep tests short and focused (mandatory)

A test should fit on one screen. If it doesn't, the setup is too complex or the test is doing too much. Apply the same coding standards you use in production code: clear variable names, no duplication, small methods.

### One class tests one method (strongly recommended)

Organize test classes around the method under test. Name the class after the method and the class being tested, e.g. `GetUserById_UserServiceTest` or `CalculateTotal_OrderServiceTest`. This makes it obvious where to look when something breaks.

### Naming: underscores, not camelCase (mandatory)

Test method names use underscores with explicit descriptions. An outsider should understand the test's purpose from the name alone. This applies to both Java `@Test` methods and JS/TS `it()` / `test()` descriptions.

```java
// Good — reads like a sentence
void find_by_email_returns_empty_when_email_not_registered()
void create_order_throws_when_cart_is_empty()
void calculate_discount_applies_10_percent_for_premium_users()

// Bad — vague or camelCase
void testFindByEmail()
void test1()
void shouldWork()
```

```typescript
// Good
it('renders_error_alert_when_api_returns_500', ...)
it('disables_submit_button_when_form_is_invalid', ...)

// Bad
it('should work', ...)
it('renders correctly', ...)
```

---

## Independence and Reliability

### Tests must be independent (mandatory)

Removing or reordering tests must not break anything. No test should depend on another test's side effects. No shared mutable state between tests.

### Tests must be deterministic (mandatory)

Use fixed datasets. Never rely on `Instant.now()`, `LocalDate.now()`, `new Date()`, `Math.random()`, or any non-deterministic input. Inject clocks or freeze time explicitly.

```java
// Good
var fixedDate = LocalDate.of(2026, 3, 15);

// Bad
var today = LocalDate.now();
```

### Never delete a failing test to make CI green (mandatory)

When a test fails after a code change, analyze why. The test might be catching a real bug. Only change the test if the behavior it asserted is intentionally different now — and update the test to match the new expected behavior.

---

## Assertions

### Assert only what matters (mandatory)

Make precise, case-specific assertions. Don't assert every field of an object when you only care about two. Over-asserting makes tests brittle and hides what's actually being verified.

```java
// Good — tests exactly what matters
assertThat(result.status()).isEqualTo("ACTIVE");
assertThat(result.email()).isEqualTo("alice@example.com");

// Bad — tests everything, obscures intent
assertThat(result).isEqualTo(expectedFullObject);
```

### Test both success and error cases (mandatory)

Every tested method should have at least one success case and one error/edge case. If a method throws exceptions, validate that it throws the right ones.

---

## Mocking Strategy

### Use mocks appropriately (mandatory)

Ask the tech lead for guidance on mocking boundaries. A test that consists entirely of mock setups and `verify()` calls tests the test, not the code.

### Too many mocks = too much coupling (mandatory)

If setting up a test requires mocking 5+ dependencies, the production code likely has a design problem. Flag it for refactoring rather than building a fragile test.

### Prefer fakes for domain logic

For domain-layer tests, manual fakes (in-memory implementations of ports) are more readable and trustworthy than mocks. Reserve mocks for infrastructure boundaries.

---

## Integration Tests

### Keep integration test scope narrow (mandatory)

When testing against real infrastructure (database, message broker), limit to success cases and a few critical error paths. Don't replicate every unit test scenario at the integration level — that's expensive and slow.

---

## Coverage and Exclusions

### Coverage exclusions require tech lead approval (mandatory)

If coverage thresholds can't be met, specific classes can be excluded (e.g. Spring `@Configuration` classes, simple DTOs with only getters/setters). This must be validated by the tech lead.

---

## Mutation Testing

Coverage tells you a line *ran*; it does not tell you a test would *fail* if that line were wrong. Mutation testing closes that gap: a tool (PIT for Java) makes small, systematic changes to the production code — flip a `<` to `<=`, negate a condition, replace a boolean return with `true`, drop a method call — and re-runs the tests. If a mutant survives (tests still pass), some behaviour is unasserted. This is the honest measure of whether your assertions actually catch bugs.

### When to use it (recommended for critical deterministic logic)

Mutation testing pays off most on **pure, deterministic decision logic** where a subtle boundary or negation error is both easy to introduce and expensive to ship: guardrails, confidence thresholds, classifiers, money/reconciliation maths, parsing/segmentation. It is not a blanket requirement for every class — DTOs, wiring/config, and thin adapters get little from it. Scope the run to the packages that matter; a scoped run stays fast and gives high signal.

Run it on the critical logic **before QA acceptance** of a story that touches such logic, and treat surviving mutants like review findings.

### How to read the result

- **Mutation score** = killed / total mutations. The headline number.
- **Test strength** = killed / mutations that were *covered* (excludes `NO_COVERAGE`). Tells you assertion quality independent of coverage gaps.
- **SURVIVED** = the code was exercised but no assertion pinned the mutated behaviour → a real assertion gap (or an equivalent mutant that cannot be observed).
- **NO_COVERAGE** = the mutated line was never executed by any test → a coverage gap, not an assertion gap.

### What to do with survivors

For each survivor, decide: **kill it or accept it.**

- **Kill** the ones that reveal a genuine gap — usually by adding a *boundary* case (a value exactly on a threshold pins `<` vs `<=`) or a *discriminating* case (an input that reaches the mutated return with the opposite outcome). These tests double as executable documentation of the exact rule.
- **Accept**, explicitly and with a reason, equivalent mutants (no observable behavioural difference) and low-value peripheral survivors. Record the rationale so the residual is a decision, not an oversight.

### Threshold policy

Put mutation testing behind its own build profile so the normal `mvn test` loop stays fast. Set a **starting `mutationThreshold` below the measured baseline** (e.g. baseline 90 % → threshold 85 %): high enough to catch a regression, low enough not to flake on minor fluctuations. Ratchet the threshold up as survivors are killed. Record the baseline (mutations / killed / test strength) so the ratchet has a reference.

For the Java/Maven wiring (PIT `pitest-maven` + `pitest-junit5-plugin`, scoping, the recompile gotcha, JDK notes), see the `java-backend-developer` skill.

---

## Architecture and Infrastructure Tests

### ArchUnit for module dependencies (optional)

Use ArchUnit to enforce package dependency rules (e.g. domain doesn't import infrastructure). Not mandatory but strongly recommended for hexagonal projects.

### Liquibase with TestContainers (optional)

Test database migrations using TestContainers for confidence that Liquibase scripts run cleanly. Not mandatory but valuable for projects with complex schema evolution.

---

## Frontend-Specific Rules

### No snapshot tests in Jest/React (mandatory)

Never use `expect(...).toMatchSnapshot()`. Snapshots are brittle, produce unreadable diffs, and developers rubber-stamp updates without reviewing them. Assert specific elements, text, or behavior instead.

```typescript
// Good
expect(screen.getByRole('heading')).toHaveTextContent('Dashboard');

// Bad
expect(container).toMatchSnapshot();
```

---

## Quick Checklist

Before submitting a test, verify:

- [ ] GIVEN / WHEN / THEN comments present (one of each, in order)
- [ ] Test name uses underscores and clearly describes the scenario
- [ ] Test is independent — no dependency on other tests or execution order
- [ ] Fixed data — no `now()`, `random()`, or non-deterministic inputs
- [ ] Assertions are specific to what's being tested
- [ ] Both success and error cases covered
- [ ] Mocks are minimal and justified
- [ ] Fits on one screen
- [ ] No snapshot assertions (frontend)
