# ArchUnit Test Reference

Complete examples of ArchUnit tests for enforcing hexagonal architecture, DDD patterns, and coding conventions.

## Maven Dependency

```xml
<dependency>
    <groupId>com.tngtech.archunit</groupId>
    <artifactId>archunit-junit5</artifactId>
    <version>1.2.1</version>
    <scope>test</scope>
</dependency>
```

## Hexagonal Architecture Tests

```java
@AnalyzeClasses(packages = "com.cursor.dashboard")
class HexagonalArchitectureTest {

    // Domain layer must be pure - no infrastructure dependencies
    @ArchTest
    static final ArchRule domainShouldNotDependOnInfrastructure =
        noClasses()
            .that().resideInAPackage("..domain..")
            .should().dependOnClassesThat()
            .resideInAPackage("..infrastructure..");

    @ArchTest
    static final ArchRule domainShouldNotDependOnApplication =
        noClasses()
            .that().resideInAPackage("..domain..")
            .should().dependOnClassesThat()
            .resideInAPackage("..application..");

    // Application layer can only depend on domain
    @ArchTest
    static final ArchRule applicationShouldOnlyDependOnDomain =
        noClasses()
            .that().resideInAPackage("..application..")
            .should().dependOnClassesThat()
            .resideInAPackage("..infrastructure..");

    // Domain should not use Spring annotations
    @ArchTest
    static final ArchRule domainShouldNotUseSpring =
        noClasses()
            .that().resideInAPackage("..domain..")
            .should().dependOnClassesThat()
            .resideInAnyPackage("org.springframework..");
}
```

## DDD Pattern Tests

```java
@AnalyzeClasses(packages = "com.cursor.dashboard")
class DddArchitectureTest {

    // Ports must be interfaces
    @ArchTest
    static final ArchRule portsShouldBeInterfaces =
        classes()
            .that().resideInAPackage("..domain.port..")
            .should().beInterfaces();

    // Value objects should be records or final classes
    @ArchTest
    static final ArchRule valueObjectsShouldBeRecordsOrFinal =
        classes()
            .that().resideInAPackage("..domain.model.valueobject..")
            .should().haveModifier(JavaModifier.FINAL)
            .orShould().beRecords();

    // Entities should be final classes
    @ArchTest
    static final ArchRule entitiesShouldBeFinal =
        classes()
            .that().resideInAPackage("..domain.model.entity..")
            .should().haveModifier(JavaModifier.FINAL);

    // Domain exceptions should extend RuntimeException
    @ArchTest
    static final ArchRule domainExceptionsShouldExtendRuntimeException =
        classes()
            .that().resideInAPackage("..domain.exception..")
            .should().beAssignableTo(RuntimeException.class);
}
```

## Naming Convention Tests

```java
@AnalyzeClasses(packages = "com.cursor.dashboard")
class NamingConventionsTest {

    // Controllers should end with "Controller"
    @ArchTest
    static final ArchRule controllersShouldBeNamedCorrectly =
        classes()
            .that().resideInAPackage("..rest..")
            .and().areAnnotatedWith(RestController.class)
            .should().haveSimpleNameEndingWith("Controller");

    // Adapters should end with "Adapter"
    @ArchTest
    static final ArchRule adaptersShouldBeNamedCorrectly =
        classes()
            .that().resideInAPackage("..adapter.out..")
            .and().areNotInterfaces()
            .and().areNotAnnotatedWith(Configuration.class)
            .should().haveSimpleNameEndingWith("Adapter");

    // Ports should end with "Port" or "UseCase"
    @ArchTest
    static final ArchRule portsShouldBeNamedCorrectly =
        classes()
            .that().resideInAPackage("..domain.port..")
            .should().haveSimpleNameEndingWith("Port")
            .orShould().haveSimpleNameEndingWith("UseCase");

    // Services should end with "Service"
    @ArchTest
    static final ArchRule servicesShouldBeNamedCorrectly =
        classes()
            .that().resideInAPackage("..application.service..")
            .should().haveSimpleNameEndingWith("Service");

    // DTOs should end with "Dto" or be records
    @ArchTest
    static final ArchRule dtosShouldBeNamedCorrectly =
        classes()
            .that().resideInAPackage("..rest.dto..")
            .should().haveSimpleNameEndingWith("Dto")
            .orShould().beRecords();
}
```

## Coding Standards Tests

```java
@AnalyzeClasses(packages = "com.cursor.dashboard")
class CodingConventionsTest {

    // No field injection - use constructor injection
    @ArchTest
    static final ArchRule noFieldInjection =
        noFields()
            .should().beAnnotatedWith(Autowired.class)
            .orShould().beAnnotatedWith(Inject.class);

    // Classes in domain should not be annotated with Spring annotations
    @ArchTest
    static final ArchRule domainClassesShouldNotBeSpringBeans =
        noClasses()
            .that().resideInAPackage("..domain..")
            .should().beAnnotatedWith(Component.class)
            .orShould().beAnnotatedWith(Service.class)
            .orShould().beAnnotatedWith(Repository.class);

    // Application services should use constructor injection
    @ArchTest
    static final ArchRule applicationServicesShouldHaveConstructorInjection =
        constructors()
            .that().areDeclaredInClassesThat()
            .resideInAPackage("..application.service..")
            .should().haveRawParameterTypes(that ->
                !that.isEmpty()); // At least one dependency

    // Controllers should only call application layer
    @ArchTest
    static final ArchRule controllersShouldOnlyUseApplicationLayer =
        classes()
            .that().resideInAPackage("..rest..")
            .should().onlyAccessClassesThat()
            .resideInAnyPackage(
                "..rest..",
                "..application..",
                "..domain.model..",
                "..domain.port.in..",
                "java..",
                "jakarta..",
                "org.springframework.."
            );
}
```

## Test Organization

```java
@AnalyzeClasses(packages = "com.cursor.dashboard")
class TestOrganizationTest {

    // Tests should mirror main structure
    @ArchTest
    static final ArchRule testClassesShouldEndWithTest =
        classes()
            .that().resideInAPackage("..test..")
            .and().areNotInterfaces()
            .and().doNotHaveSimpleName("Fake.*")
            .should().haveSimpleNameEndingWith("Test");

    // Fake adapters should be in fake package
    @ArchTest
    static final ArchRule fakeAdaptersShouldBeInFakePackage =
        classes()
            .that().haveSimpleNameStartingWith("Fake")
            .should().resideInAPackage("..fake..");
}
```

## Running ArchUnit Tests

```bash
# Run all ArchUnit tests
mvn test -Dtest=*ArchitectureTest,*ConventionsTest

# Run specific test class
mvn test -Dtest=HexagonalArchitectureTest
```

## Common Violations and Fixes

| Violation | Fix |
|-----------|-----|
| Domain depends on infrastructure | Move dependency to port interface |
| Field injection found | Convert to constructor injection |
| Port is not an interface | Convert class to interface |
| Service in domain package | Move to application/service |
| Spring annotation in domain | Remove annotation, use pure Java |
