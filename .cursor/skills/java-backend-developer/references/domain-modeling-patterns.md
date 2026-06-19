# Domain Modeling Patterns — Full Reference

Detailed examples for value objects, money handling, ratios, and typed identifiers.

## Money (Value Object with BigDecimal + Currency)

Floating-point types (`double`, `float`) cannot represent decimal currency accurately — `0.1 + 0.2 != 0.3` in IEEE 754. Bare `long` cents lose currency context and push conversion logic into callers. A dedicated `Money` value object solves both problems.

### The Money Value Object

```java
package com.cursor.dashboard.domain.model.valueobject;

import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.Currency;
import java.util.Objects;

public record Money(BigDecimal amount, Currency currency) {

    public static final Currency USD = Currency.getInstance("USD");
    public static final Currency EUR = Currency.getInstance("EUR");
    private static final int SCALE = 2;

    public Money {
        Objects.requireNonNull(amount, "Amount is required");
        Objects.requireNonNull(currency, "Currency is required");
        amount = amount.setScale(SCALE, RoundingMode.HALF_UP);
    }

    public static Money of(BigDecimal amount, Currency currency) {
        return new Money(amount, currency);
    }

    public static Money ofCents(long cents, Currency currency) {
        return new Money(BigDecimal.valueOf(cents, SCALE), currency);
    }

    public static Money usd(BigDecimal amount) {
        return new Money(amount, USD);
    }

    public static Money usd(String amount) {
        return new Money(new BigDecimal(amount), USD);
    }

    public static Money zero(Currency currency) {
        return new Money(BigDecimal.ZERO, currency);
    }

    public Money add(Money other) {
        requireSameCurrency(other);
        return new Money(amount.add(other.amount), currency);
    }

    public Money subtract(Money other) {
        requireSameCurrency(other);
        return new Money(amount.subtract(other.amount), currency);
    }

    public Money multiply(int quantity) {
        return new Money(amount.multiply(BigDecimal.valueOf(quantity)), currency);
    }

    public long toCents() {
        return amount.movePointRight(SCALE).longValueExact();
    }

    public boolean isPositive() {
        return amount.signum() > 0;
    }

    public boolean isNegative() {
        return amount.signum() < 0;
    }

    private void requireSameCurrency(Money other) {
        if (!currency.equals(other.currency)) {
            throw new IllegalArgumentException(
                "Cannot combine " + currency + " with " + other.currency);
        }
    }
}
```

### Usage in Domain Entities

```java
public record TeamMember(
    UserId id, String name, Email email,
    long totalRequests, long totalTokens,
    Money spend,
    AcceptanceRatio acceptanceRatio, boolean active
) {
    public TeamMember {
        Objects.requireNonNull(id, "User ID is required");
        Objects.requireNonNull(spend, "Spend is required");
        // ...
    }
}
```

### Usage in DTOs

Serialize as cents (long) or decimal string depending on the API contract:

```java
public record TeamMemberDto(
    String id, String name, String email,
    long totalRequests, long totalTokens,
    long spendCents,
    int acceptanceRatePercent, boolean active
) {
    public static TeamMemberDto fromDomain(TeamMember entity) {
        return new TeamMemberDto(
            entity.id().value(), entity.name(), entity.email().value(),
            entity.totalRequests(), entity.totalTokens(),
            entity.spend().toCents(),
            entity.acceptanceRatio().asPercentage(), entity.active()
        );
    }
}
```

### Conversion at Adapter Boundaries

External APIs often return money as `double` or `long` cents. Convert into `Money` at the adapter layer — never let raw numeric money leak into the domain.

```java
// Adapter receiving cents as long from an external API
long rawCents = jsonNode.get("overallSpendCents").asLong();
Money spend = Money.ofCents(rawCents, Money.USD);

// Adapter receiving dollars as double from an external API
double rawDollars = jsonNode.get("chargedAmount").asDouble();
Money cost = Money.usd(BigDecimal.valueOf(rawDollars));
```

## Ratios and Percentages

Ratios (0.0–1.0) and percentages (0–100) are easy to confuse. A value object eliminates this ambiguity and provides conversion methods.

```java
public record AcceptanceRatio(double value) {
    public AcceptanceRatio {
        if (value < 0.0 || value > 1.0) {
            throw new IllegalArgumentException(
                "Acceptance ratio must be between 0.0 and 1.0");
        }
    }

    public int asPercentage() {
        return (int) Math.round(value * 100);
    }

    public static AcceptanceRatio fromPercentage(int percentage) {
        return new AcceptanceRatio(percentage / 100.0);
    }

    public static AcceptanceRatio zero() {
        return new AcceptanceRatio(0.0);
    }
}
```

Use the value object in domain entities (`AcceptanceRatio`), and convert to `int` percentage only in DTOs where the API contract requires it. This keeps the domain free from ambiguity about whether `75` means 75% or 0.75.

## Typed Identifiers

Raw `String` IDs are easy to mix up — passing a `userId` where a `teamId` is expected compiles fine but fails at runtime. Typed ID wrappers make these bugs impossible.

```java
public record UserId(String value) {
    public UserId {
        if (value == null || value.isBlank()) {
            throw new InvalidUserIdException("null or empty");
        }
        if (value.length() < 3 || value.length() > 50) {
            throw new InvalidUserIdException(value);
        }
    }

    @Override
    public String toString() { return value; }
}
```

Create a typed ID whenever an identifier is passed between layers or used as a map key. In DTOs, unwrap back to `String` via `.value()`.

## Email

Validate format at construction time so invalid emails never enter the domain.

```java
public record Email(String value) {
    private static final Pattern EMAIL_PATTERN = Pattern.compile(
        "^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\\.[a-zA-Z]{2,}$"
    );

    public Email {
        if (value == null || value.isBlank()) {
            throw new InvalidEmailException("null or empty");
        }
        if (!EMAIL_PATTERN.matcher(value).matches()) {
            throw new InvalidEmailException(value);
        }
    }
}
```

## DateRange

Enforces business constraints at construction time — dates must be ordered, range must not exceed the API limit.

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

## When to Create a Value Object

| Signal | Action |
|--------|--------|
| A primitive carries domain meaning (email, money, ratio) | Wrap in a value object |
| Two primitives of the same type can be confused (`userId` vs `teamId`) | Create typed wrappers |
| A value has constraints (0–100, positive-only, format rules) | Validate in compact constructor |
| A value needs formatting or conversion (cents ↔ dollars, ratio ↔ percent) | Add conversion methods to the value object |
| A primitive is only used internally with no cross-layer risk | Keep it primitive (`long totalRequests`) |
