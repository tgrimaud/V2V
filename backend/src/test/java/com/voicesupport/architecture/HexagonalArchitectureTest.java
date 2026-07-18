package com.voicesupport.architecture;

import com.tngtech.archunit.core.importer.ImportOption;
import com.tngtech.archunit.junit.AnalyzeClasses;
import com.tngtech.archunit.junit.ArchTest;
import com.tngtech.archunit.lang.ArchRule;

import static com.tngtech.archunit.lang.syntax.ArchRuleDefinition.classes;
import static com.tngtech.archunit.lang.syntax.ArchRuleDefinition.fields;
import static com.tngtech.archunit.lang.syntax.ArchRuleDefinition.noClasses;

@AnalyzeClasses(packages = "com.voicesupport", importOptions = ImportOption.DoNotIncludeTests.class)
class HexagonalArchitectureTest {

    @ArchTest
    static final ArchRule domainShouldNotDependOnInfrastructure =
            noClasses()
                    .that().resideInAPackage("..domain..")
                    .should().dependOnClassesThat().resideInAPackage("..infrastructure..");

    @ArchTest
    static final ArchRule domainShouldNotDependOnApplication =
            noClasses()
                    .that().resideInAPackage("..domain..")
                    .should().dependOnClassesThat().resideInAPackage("..application..");

    @ArchTest
    static final ArchRule applicationShouldNotDependOnInfrastructure =
            noClasses()
                    .that().resideInAPackage("..application..")
                    .should().dependOnClassesThat().resideInAPackage("..infrastructure..");

    @ArchTest
    static final ArchRule domainShouldNotUseSpring =
            noClasses()
                    .that().resideInAPackage("..domain..")
                    .should().dependOnClassesThat().resideInAnyPackage("org.springframework..");

    @ArchTest
    static final ArchRule portsShouldBeInterfaces =
            classes()
                    .that().resideInAPackage("..domain.port..")
                    .should().beInterfaces();

    @ArchTest
    static final ArchRule valueObjectsShouldBeRecordsOrFinal =
            classes()
                    .that().resideInAPackage("..domain.model.valueobject..")
                    .should().beRecords()
                    .orShould().haveModifier(com.tngtech.archunit.core.domain.JavaModifier.FINAL);

    @ArchTest
    static final ArchRule noFieldInjection =
            fields()
                    .should().notBeAnnotatedWith("org.springframework.beans.factory.annotation.Autowired");
}
