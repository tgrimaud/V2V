---
name: code-guidelines
description: >-
  Enforce team code quality standards: method size (20 lines), class size (200 lines),
  nesting depth (3 levels), comment policy, library/dependency governance, REST naming,
  refactoring safety, list index access, and persistence technology choices.
  Use when writing, reviewing, or refactoring production code. Triggers on: "write a method",
  "add a class", "refactor this", "code review", "review this code", "add a dependency",
  "new library", "add to pom.xml", "REST endpoint", "clean up", "this method is too long",
  "reduce complexity", "too many lines", "too deeply nested", "upgrade library version",
  "version bump". Applies primarily to Java/Spring backend but size, depth, and comment
  principles apply to any language in the project.
---

# Code Guidelines

Practical rules for writing clean, maintainable, and safe production code. These aren't arbitrary limits — each rule exists because the team has seen real problems when they're ignored.

---

## Size and Complexity

### Method size: 20 lines max (mandatory)

Count only non-blank lines. A method that exceeds 20 lines is doing too much — extract helpers, compose smaller pieces, or rethink the approach. Short methods are easier to name, test, and reason about.

```java
// Too long — doing validation, transformation, and persistence in one method.
// Split into validate(), transform(), and persist().

// Good — each method has a single responsibility and fits in ~10-15 lines.
public OrderConfirmation placeOrder(OrderRequest request) {
    var validated = validate(request);
    var order = buildOrder(validated);
    return repository.save(order).toConfirmation();
}
```

### Class size: 200 lines max (mandatory)

Count only non-blank lines. When a class grows beyond this, it's accumulating responsibilities. Split by cohesion: group methods that change together into their own class.

### Method nesting depth: 3 levels max (mandatory)

Deeply nested code is hard to follow and test. If you're inside an `if` inside a `for` inside a `try`, stop — extract the inner logic into a named method, or invert conditions with early returns.

```java
// Bad — depth 4
void process(List<Order> orders) {
    for (var order : orders) {
        if (order.isValid()) {
            for (var item : order.items()) {
                if (item.inStock()) {   // depth 4 — too deep
                    ship(item);
                }
            }
        }
    }
}

// Good — flat and readable
void process(List<Order> orders) {
    orders.stream()
        .filter(Order::isValid)
        .flatMap(order -> order.items().stream())
        .filter(Item::inStock)
        .forEach(this::ship);
}
```

---

## Comments and Clarity

### If you need a comment, the code might need refactoring (guideline)

A comment that explains *what* the code does usually means the code isn't clear enough. Before adding a comment, try renaming variables, extracting methods, or simplifying the logic so the code speaks for itself.

Comments are appropriate for:
- **Why** — non-obvious business rules, regulatory constraints, workarounds for known issues
- **Contracts** — public API boundaries consumed by external teams
- **Warnings** — performance traps, thread-safety notes, "do not change without updating X"

Comments are **not** appropriate for:
- Narrating what the code does (`// increment counter`)
- Restating the method name (`// Gets the user by ID`)
- Compensating for vague names or tangled logic — fix the code instead

---

## Library and Dependency Management

### No new libraries without tech lead approval (mandatory)

Adding a dependency affects build time, binary size, security surface, and long-term maintenance. Before adding a library to `pom.xml` (or `package.json`), get explicit approval from the tech lead. Come prepared with:
- What problem does it solve?
- Why can't you solve it with what's already in the project?
- What are the alternatives?

### Vet new libraries before proposing them (mandatory)

Every external library you propose must meet these criteria:

| Check | What to verify |
|-------|---------------|
| **Source** | Hosted on a public repository (GitHub, GitLab, etc.) |
| **Maintenance** | Active commits within the last 6 months, responsive issue tracker |
| **License** | Compatible with the project (Apache 2.0, MIT are safe; GPL may not be) |
| **Community** | Meaningful adoption — stars, downloads, usage in production projects |

If a library fails any of these checks, it's a risk. Raise it with the team before proceeding.

### Version upgrades require regression testing (mandatory)

Any version update of an external component — JDK, libraries, database drivers, message brokers, even minor/patch versions — requires re-running the main success-case tests before merging. "It's just a patch" is how subtle regressions sneak into production.

At a minimum: run `mvn test` (backend) and `npm run test:run` (frontend). For infrastructure changes (JDK, database, broker), also run integration and E2E tests to catch behavioral shifts that unit tests won't catch.

### Unit-test all library surface area you use (mandatory)

Every feature of an external library that your code depends on must be covered by a unit test. When the library is upgraded, running the test suite should immediately reveal any behavioral changes or breaking API shifts. If you call `library.doThing()` in production code, there should be a test that exercises `doThing()` and asserts on its output.

---

## Data Access

### Don't assume Hibernate/JPA (guideline)

The persistence layer should use the technology that fits the use case. Hibernate is not always the right answer:

| Use case | Consider |
|----------|---------|
| Simple CRUD with complex object graphs | JPA/Hibernate |
| Read-heavy reporting, bulk queries | Spring JDBC / jOOQ |
| Full control over SQL, performance-critical | Plain JDBC / jOOQ |
| Document-oriented data | MongoDB driver / Spring Data Mongo |

Choose deliberately and justify the decision.

### Never access list elements by index (mandatory)

Accessing `list.get(1)` (or any hardcoded index) creates a fragile, order-dependent coupling. If the list changes shape, size, or sort order, the code breaks silently or throws `IndexOutOfBoundsException`. This also applies to index-based iteration (`for (int i = 0; ...)`) when the index is used to access elements — prefer enhanced for-loops or streams.

```java
// Bad — assumes position
var secondItem = results.get(1);

// Bad — index-based iteration
for (int i = 0; i < results.size(); i++) {
    process(results.get(i));
}

// Good — find by criteria
var targetItem = results.stream()
    .filter(r -> r.type().equals(expectedType))
    .findFirst()
    .orElseThrow(() -> new ItemNotFoundException(expectedType));

// Good — enhanced for-loop
for (var result : results) {
    process(result);
}
```

---

## REST API Design

### Follow REST naming best practices (mandatory)

Endpoints must follow established conventions. When in doubt, consult the team's Confluence page or ask the tech lead.

| Rule | Example |
|------|---------|
| Plural nouns for collections | `/api/orders`, not `/api/order` |
| Kebab-case for multi-word | `/api/order-items`, not `/api/orderItems` |
| No verbs in paths | `POST /api/orders`, not `/api/create-order` |
| Nested resources for relationships | `/api/teams/{id}/members` |
| Query params for filtering/sorting | `/api/orders?status=pending&sort=created_at` |

---

## Refactoring Safety

### Test before you refactor (mandatory)

Before touching existing code for a refactoring:

1. **Verify test coverage** — the code you're about to change must have tests. If it doesn't, write them first against the current behavior.
2. **Run the tests** — confirm they all pass before making any changes.
3. **Refactor** — make your changes.
4. **Run the tests again** — all existing tests must still pass. If a test breaks, either your refactoring changed behavior (fix it) or the test was wrong (investigate before changing it).

Refactoring without tests is guessing.

### Leave it cleaner than you found it — the Boy Scout Rule (guideline)

When you edit a file, bring the code you touch up to the current standard instead of matching the surrounding legacy style. Small, in-passing cleanups (a misleading name, a stale comment, a convention drift like a test method that doesn't follow the naming rule) keep the codebase converging on the standard instead of ossifying around old choices. Consistency is what makes a codebase readable, so the standard wins over "matching the neighbours".

Keep it bounded and safe:
- **Scope to what you touch.** Clean the file/section you're already editing for a ticket. Don't launch an unrelated big-bang migration — leave untouched files for whoever edits them next.
- **Behaviour-preserving only.** A cleanup must not change behaviour. Cover it with the same "test before / test after" loop above; a pure rename or comment fix should keep every test green.
- **Separate the intent in the diff.** Where practical, keep the cleanup as its own commit (e.g. `refactor(test): …`) so reviewers can tell mechanical cleanup from real change.
- **Respect real constraints.** Some "inconsistencies" are mandatory — e.g. methods that override an interface must keep the interface's name. Don't "clean" those.

The goal is convergence, not perfection in one pass: every touched file gets a little better, and the standard spreads by attrition rather than by a risky one-shot rewrite.

---

## Environment and Pipeline Safety

### Verify the pipeline after merging (mandatory)

After your merge request is merged, check that the CI/CD pipeline succeeded on the target branch. Don't assume it passed — merges can introduce conflicts or ordering issues that weren't visible in the MR pipeline. If it fails, you own the fix.

### Never connect local to third-party environments (mandatory)

Never point your local development environment at another team's infrastructure — especially databases, message brokers, or APIs in qualification/staging/production. This risks data corruption, unexpected side effects, and security violations.

If cross-environment access is absolutely necessary:
- Use **read-only credentials** only
- Get explicit approval from the environment owner
- Document the access and its duration

---

## Quick Checklist

Before submitting code, verify:

- [ ] No method exceeds 20 non-blank lines
- [ ] No class exceeds 200 non-blank lines
- [ ] No method nesting deeper than 3 levels
- [ ] Comments explain *why*, not *what* — or code was refactored to be self-explanatory
- [ ] Code touched in this change was brought up to standard (Boy Scout Rule), behaviour-preserving
- [ ] No new dependencies added without tech lead approval
- [ ] New libraries vetted (public repo, active maintenance, license check)
- [ ] Library features used in production are covered by unit tests
- [ ] No hardcoded list index access (`list.get(n)`)
- [ ] REST endpoints follow naming conventions (plural, kebab-case, no verbs)
- [ ] Refactored code was tested before and after changes
- [ ] Pipeline verified on target branch after merge
- [ ] No local-to-third-party environment connections
