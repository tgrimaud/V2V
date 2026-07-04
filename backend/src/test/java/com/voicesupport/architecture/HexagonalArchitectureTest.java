package com.voicesupport.architecture;

import com.tngtech.archunit.core.domain.JavaClasses;
import com.tngtech.archunit.core.importer.ClassFileImporter;
import com.tngtech.archunit.core.importer.ImportOption;
import com.tngtech.archunit.lang.ArchRule;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;

import static com.tngtech.archunit.lang.syntax.ArchRuleDefinition.classes;
import static com.tngtech.archunit.lang.syntax.ArchRuleDefinition.noClasses;

class HexagonalArchitectureTest {

    private static final String BASE_PACKAGE = "com.voicesupport";

    private static JavaClasses productionClasses;

    @BeforeAll
    static void importClasses() {
        productionClasses = new ClassFileImporter()
                .withImportOption(ImportOption.Predefined.DO_NOT_INCLUDE_TESTS)
                .importPackages(BASE_PACKAGE);
    }

    @Test
    void domain_should_not_depend_on_infrastructure() {
        // GIVEN
        ArchRule rule = noClasses()
                .that().resideInAPackage("..domain..")
                .should().dependOnClassesThat().resideInAPackage("..infrastructure..");

        // WHEN / THEN
        rule.check(productionClasses);
    }

    @Test
    void domain_should_not_depend_on_spring_framework() {
        // GIVEN
        ArchRule rule = noClasses()
                .that().resideInAPackage("..domain..")
                .should().dependOnClassesThat().resideInAPackage("org.springframework..");

        // WHEN / THEN
        rule.check(productionClasses);
    }

    @Test
    void domain_should_not_depend_on_reactor() {
        // GIVEN
        ArchRule rule = noClasses()
                .that().resideInAPackage("..domain..")
                .should().dependOnClassesThat().resideInAPackage("reactor..");

        // WHEN / THEN
        rule.check(productionClasses);
    }

    @Test
    void input_adapters_should_not_depend_on_domain_services() {
        // GIVEN
        ArchRule rule = noClasses()
                .that().resideInAPackage("..infrastructure.adapter.in..")
                .should().dependOnClassesThat().resideInAPackage("..domain.service..");

        // WHEN / THEN
        rule.check(productionClasses);
    }

    @Test
    void input_adapters_should_not_depend_on_output_ports() {
        // GIVEN
        ArchRule rule = noClasses()
                .that().resideInAPackage("..infrastructure.adapter.in..")
                .should().dependOnClassesThat().resideInAPackage("..domain.port.out..");

        // WHEN / THEN
        rule.check(productionClasses);
    }

    @Test
    void ports_should_be_interfaces() {
        // GIVEN
        ArchRule rule = classes()
                .that().resideInAPackage("..domain.port..")
                .should().beInterfaces();

        // WHEN / THEN
        rule.check(productionClasses);
    }

    @Test
    void spring_configuration_should_only_live_in_infrastructure_config() {
        // GIVEN
        ArchRule rule = noClasses()
                .that().resideOutsideOfPackage("..infrastructure.config..")
                .should().beAnnotatedWith("org.springframework.context.annotation.Configuration");

        // WHEN / THEN
        rule.check(productionClasses);
    }
}
