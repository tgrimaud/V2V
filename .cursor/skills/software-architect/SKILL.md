---
name: software-architect
description: >-
  Software architecture patterns for building maintainable, modular, and microservices-ready
  applications. Covers hexagonal architecture (ports & adapters), GoF design patterns,
  DDD tactical patterns, the Hive pattern for modular monoliths, feature-based frontend
  modularization, and architecture enforcement with ArchUnit. Use proactively when designing
  new modules, extracting bounded contexts, restructuring packages, defining port/adapter
  boundaries, applying design patterns, deciding between modular monolith vs. microservices,
  discussing architecture trade-offs, or reviewing code for architectural violations. Also
  use when the user mentions "architecture", "hexagonal", "ports and adapters", "DDD",
  "bounded context", "modular monolith", "microservices extraction", "the Hive", "layer
  rules", "dependency direction", "design patterns", "GoF", or "feature modules".
---

# Software Architect

Architecture patterns and principles for building systems that are modular by design, testable in isolation, and ready for extraction into microservices when the business demands it — without requiring an architectural rewrite.

This skill owns the **structural decisions**. Language-specific implementation details (Spring annotations, Java records, React hooks) live in their respective skills (`java-backend-developer`, `react-frontend-developer`). This skill tells you *what* the architecture looks like and *why*; those skills tell you *how* to implement it.

---

## Hexagonal Architecture (Ports & Adapters)

The system follows Alistair Cockburn's hexagonal architecture. The core idea: business logic sits at the center, completely isolated from technical concerns. External systems (databases, APIs, UIs) connect through ports (interfaces) and adapters (implementations).

### Package Structure (Backend)

```
com.{company}.{project}/
├── domain/
│   ├── model/
│   │   ├── aggregate/      # Aggregate roots
│   │   ├── entity/         # Entities with identity
│   │   └── valueobject/    # Immutable value objects
│   ├── service/            # Domain services (pure logic, no framework)
│   ├── exception/          # Domain exceptions
│   ├── factory/            # Factories and builders
│   └── port/
│       ├── out/            # Output ports — app calls external systems
│       └── in/             # Input ports (use case interfaces) — optional
├── application/
│   └── service/            # Application services (orchestration, caching)
└── infrastructure/
    ├── adapter/
    │   ├── out/            # Output adapters (DB, API clients, mock)
    │   │   ├── mock/       # Dev/test implementations
    │   │   └── {system}/   # Named by system (e.g., cursor/, stripe/)
    │   └── in/
    │       └── rest/       # Input adapters (REST controllers)
    │           └── dto/    # Request/Response DTOs
    └── config/             # Framework configuration (Spring, etc.)
```

### Feature Structure (Frontend)

```
src/
├── features/               # Feature modules (bounded contexts)
│   └── {feature}/
│       ├── index.ts        # Barrel export — the module's public API
│       ├── components/     # UI components
│       ├── hooks/          # Feature-specific hooks
│       ├── types/          # Feature-specific types
│       └── __tests__/      # Tests
├── shared/                 # Cross-feature reusable components
│   ├── index.ts
│   ├── components/
│   └── hooks/
└── services/               # API client, query client
```

**Barrel exports** are the frontend equivalent of ports — they define what a module exposes. Import from barrel (`@/features/usage`), never from deep paths (`@/features/usage/components/Chart`). This decouples consumers from internal structure.

### Port Naming Convention

| Direction | Port Package | Adapter Package | Purpose |
|-----------|--------------|-----------------|---------|
| **OUT** | `domain/port/out/` | `infrastructure/adapter/out/` | Application calls external systems (DB, APIs) |
| **IN** | `domain/port/in/` | `infrastructure/adapter/in/` | External world calls application (REST, CLI) |

Ports are **always interfaces**. Name them by what they do (`AnalyticsQueryPort`, `TeamQueryPort`), not by technology (`DatabaseRepository`, `HttpClient`).

### Layer Dependency Rules

The most important rule in the architecture: **dependencies point inward**.

| Layer | Can Depend On | Cannot Depend On | Framework Annotations? |
|-------|---------------|------------------|------------------------|
| Domain | Nothing (pure language) | Application, Infrastructure | **No** |
| Application | Domain | Infrastructure | **Yes** |
| Infrastructure | Domain, Application | — | **Yes** |

The domain layer is pure — no framework imports, no I/O, no annotations. It expresses business rules in plain language constructs (interfaces, records, exceptions). This makes it trivially testable and completely portable.

### Application vs. Domain Services

Getting this distinction right prevents the most common architectural violation — business logic leaking into infrastructure.

**Domain services** contain pure business rules that operate on domain entities and value objects. They have no framework dependencies, no I/O, no caching. They are registered as beans from infrastructure configuration — not annotated as services themselves.

**Application services** are the entry point for use cases. They orchestrate port calls, apply caching, handle transactions, and delegate to domain services for actual business logic. They live in the `application/` layer and carry framework annotations.

| Concern | Where it lives | Example |
|---------|---------------|---------|
| Business rule | Domain service | "Flag users with >2x average spend as anomalies" |
| Data retrieval | Application service → output port | "Fetch team members for date range" |
| Caching | Application service | `@Cacheable("team")` |
| HTTP call | Output adapter | `WebClient.get().uri(...)` |
| Request validation | Input adapter (controller) | `@Valid`, `@RequestParam` |

---

## GoF Design Patterns

The Gang of Four patterns are tools, not goals. Apply them when they solve a real problem in the current codebase — not preemptively. The patterns most relevant to hexagonal architecture:

| Pattern | Where it appears | Purpose |
|---------|-----------------|---------|
| **Strategy** | Port/Adapter boundary | A port is a strategy interface; adapters are interchangeable implementations (mock vs. real, INPROC vs. REST) |
| **Factory Method** | DTO `fromDomain()`, value object factories | Encapsulate object creation at boundaries (`Money.ofCents()`, `TeamMemberDto.fromDomain()`) |
| **Adapter** | Output adapters | Translate between the domain's port interface and an external system's API |
| **Facade** | Application services | Simplify complex domain interactions behind a single entry point for each use case |
| **Observer** | Event-driven modules (future) | Decouple modules via domain events rather than direct calls — aligns with Hive INPROC pattern |
| **Template Method** | Shared adapter base classes | Define the skeleton of an algorithm (e.g., paginated API fetching) with customizable steps |
| **Decorator** | Cross-cutting concerns | Add behavior (logging, caching, retry) without modifying the wrapped class |

When considering a pattern, ask: "Does this reduce coupling or improve clarity?" If the answer is no, the pattern is overhead.

---

## DDD Tactical Patterns

Domain-Driven Design provides a vocabulary for structuring the domain layer. These patterns keep business concepts explicit and prevent primitive obsession from eroding the model over time.

### Value Objects

Immutable objects defined by their attributes, not identity. Two value objects with the same values are equal. Use records in Java, readonly types in TypeScript.

**When to create one:**

| Signal | Action |
|--------|--------|
| A primitive carries domain meaning (email, money, ratio) | Wrap in a value object |
| Two primitives of the same type can be confused (`userId` vs `teamId`) | Create typed wrappers |
| A value has constraints (0–100, positive-only, format rules) | Validate at construction time |
| A value needs formatting or conversion (cents ↔ dollars, ratio ↔ percent) | Add conversion methods |
| A primitive is only used internally with no cross-layer risk | Keep it primitive |

**Key value object types:**

- **Money** — Never use `double` or bare `long` for monetary values. Use a dedicated value object backed by precise arithmetic (`BigDecimal` in Java). This guarantees precision and makes currency explicit.
- **Typed IDs** — Wrap identifiers (`UserId`, `TeamId`) so the compiler prevents mixing them.
- **Ratios/Percentages** — Store as ratio (0.0–1.0) internally, convert to percentage only at boundaries.
- **Email** — Validate format at construction; invalid values never enter the domain.
- **Date ranges** — Validate ordering and business constraints (e.g., max 30-day span) in the constructor.

### Entities

Objects with identity that persists across state changes. In this project, entities are immutable records — state changes produce new instances. Validation happens in the compact constructor.

### Aggregates

Clusters of entities and value objects treated as a unit for data changes. The aggregate root is the only entry point — external code never reaches inside to manipulate child entities directly.

### Ports (Interfaces)

Ports define the contract between the domain and the outside world. They are technology-agnostic interfaces:

- **Output ports** (`domain/port/out/`) — what the application needs from external systems
- **Input ports** (`domain/port/in/`) — use cases the application exposes (optional, can use application services directly)

### Domain Exceptions

Domain-specific exceptions with error codes. These are `RuntimeException` subclasses that carry a code for consistent API error responses.

### DTOs at Boundaries

DTOs live in the infrastructure layer (`adapter/in/rest/dto/`). They use **static factory methods** (`fromDomain()`) for mapping — no separate mapper classes. At adapter boundaries, convert external representations into domain types (e.g., `double` → `Money`, `String` → `UserId`). Never let raw primitives leak into the domain.

See `java-backend-developer` skill and its `references/domain-modeling-patterns.md` for full implementation examples of each pattern.

---

## The Hive Pattern

*Based on the work of Julien Topçu and Thomas Pierrain.*

The Hive is a modularization strategy for building a **microservices-ready modular monolith**. It addresses a common industry trap: rushing to microservices creates a distributed monolith — the worst of both worlds. The Hive provides a middle path.

### Core Principle

> **Build once, deploy as you wish.** Decouple your software design from your deployment strategy.

The system is designed as if it were microservices (independent modules with clear boundaries), but deployed as a single unit. When a module actually needs independent scaling or deployment, extracting it is a configuration change — not an architectural rewrite.

### How It Works

#### Step 1 — Hexagonalize each bounded context

Each bounded context (module) gets its own complete hexagonal architecture: its own domain, its own ports & adapters, its own persistence, its own controllers. Modules don't share databases or controllers.

#### Step 2 — Vertical slicing

Each module owns its full vertical slice:

```
Module A                    Module B
┌─────────────────┐        ┌─────────────────┐
│   Controller     │        │   Controller     │
│   ─────────      │        │   ─────────      │
│   Domain         │        │   Domain         │
│   ─────────      │        │   ─────────      │
│   Persistence    │        │   Persistence    │
│   ─────────      │        │   ─────────      │
│   Database       │        │   Database       │
└─────────────────┘        └─────────────────┘
```

No shared layers. Each module is independently extractable because it owns everything from API to storage.

#### Step 3 — INPROC Ports & Adapters

When modules need to communicate inside the monolith, they use **INPROC (in-process) adapters** — the same ports & adapters pattern used for external dependencies, but implemented as in-memory method calls.

```
Module A                         Module B
┌───────────┐                   ┌───────────┐
│  Domain A  │                   │  Domain B  │
│            │                   │            │
│  SPI Port ─┼── INPROC Adapter ─┼─ API Port  │
│            │   (in-memory)     │            │
└───────────┘                   └───────────┘
```

The INPROC adapter contains an **Anticorruption Layer (ACL)** that translates between module domain models. Module A speaks its own ubiquitous language; Module B speaks its own. The ACL bridges the two without either module knowing about the other's internals.

#### Step 4 — The Hived Modular Monolith

Once all bounded contexts are hexagonalized with INPROC adapters between them, you have a "hive" — a collection of independent hexagons communicating through well-defined ports. Each hexagon can evolve independently.

#### Step 5 — Scale-out / Extraction

When a module needs independent scaling (e.g., Module B is CPU-heavy while Module A is idle):

1. **Swap the INPROC adapter for a REST client adapter** in Module A
2. **Deploy Module B as a separate microservice** with its own REST API
3. Module A now calls Module B over HTTP instead of in-memory

This is a **1-line infrastructure change** (swap adapter implementation), not an architectural rewrite. The domain, ports, and business logic don't change at all.

```
Before (monolith):   A ──INPROC──> B    (in-memory call)
After (extracted):   A ──REST────> B    (HTTP call to separate service)
```

### The Fractal Nature

The pattern is **fractal**: the same ports & adapters structure applies at every level — within a module, between modules (INPROC), and between services (REST/HTTP). This consistency is what makes extraction painless.

### Test Slicing

Your test suite can be a hidden monolith. Tests must be modularized with the same rigor as production code. Each module gets its own test suite, using stubs for inter-module dependencies — mirroring the INPROC adapter pattern. When a module is extracted, its tests go with it.

### Applying the Hive to This Project

Our current architecture already follows the Hive's foundational principles:

- Each port/adapter boundary is a potential extraction point
- Output ports (`AnalyticsQueryPort`, `TeamQueryPort`) abstract external dependencies
- Mock adapters and real adapters are swappable by profile
- Domain services are framework-free and portable

**To move toward full Hive readiness**, if the system grows to warrant multiple bounded contexts:

1. Identify bounded contexts within the domain (e.g., "Analytics", "Team Management", "Forecasting")
2. Give each context its own sub-package with its own ports
3. Use INPROC adapters for cross-context communication (not direct service calls)
4. Each context should own its persistence and controllers

### References

- [Slides: Live Coding The Hive](https://slides.com/julientopcu/live-coding-the-hive) — Julien Topçu
- [Video: Live Coding The Hive](https://www.youtube.com/watch?v=VKcRNtj0tzc) — Topçu & Pierrain
- [Craft Conf 2025 Talk](https://craft-conf.com/2025/talk/julien-topcu) — "The Hive: a modularization strategy for your modular monolith or microservices"

---

## Architecture Enforcement

Architecture rules are only as good as their enforcement. Use automated tests to verify dependency direction and naming conventions.

### Principles to Enforce

1. **Domain isolation** — domain layer has no infrastructure or framework imports
2. **Dependency direction** — dependencies always point inward (infra → app → domain)
3. **Ports are interfaces** — never concrete classes
4. **No field injection** — always constructor injection
5. **Naming conventions** — Controllers end with `Controller`, Adapters with `Adapter`, Ports with `Port`
6. **No framework annotations in domain** — domain classes are never Spring beans directly

See `references/archunit-tests.md` for complete ArchUnit test examples that enforce these rules.

---

## Architecture Decision Checklist

Before making a structural change, verify:

- [ ] New module follows hexagonal structure (domain → ports → adapters)
- [ ] Domain layer has zero infrastructure dependencies
- [ ] Domain services are registered via configuration, not framework annotations
- [ ] Ports are interfaces named by business capability, not technology
- [ ] Cross-module communication goes through ports (not direct class references)
- [ ] Each module owns its vertical slice (controller, domain, persistence)
- [ ] Value objects protect against primitive obsession at domain boundaries
- [ ] DTOs map at adapter boundaries with static factory methods
- [ ] ArchUnit tests cover the new structure
- [ ] Frontend features export through barrel files
- [ ] Test suite mirrors the module structure (no hidden test monolith)
