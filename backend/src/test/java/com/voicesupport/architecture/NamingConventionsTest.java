package com.voicesupport.architecture;

import com.tngtech.archunit.core.importer.ImportOption;
import com.tngtech.archunit.junit.AnalyzeClasses;
import com.tngtech.archunit.junit.ArchTest;
import com.tngtech.archunit.lang.ArchRule;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.bind.annotation.RestController;

import static com.tngtech.archunit.lang.syntax.ArchRuleDefinition.classes;

@AnalyzeClasses(packages = "com.voicesupport", importOptions = ImportOption.DoNotIncludeTests.class)
class NamingConventionsTest {

    @ArchTest
    static final ArchRule controllersShouldBeNamedCorrectly =
            classes()
                    .that().areAnnotatedWith(RestController.class)
                    .should().haveSimpleNameEndingWith("Controller");

    @ArchTest
    static final ArchRule adaptersShouldBeNamedCorrectly =
            classes()
                    .that().resideInAPackage("..adapter.out..")
                    .and().areNotInterfaces()
                    .and().areNotAnnotatedWith(Configuration.class)
                    .and().areTopLevelClasses()
                    .should().haveSimpleNameEndingWith("Adapter")
                    // Source connectors are a first-class outbound-port family
                    // (KnowledgeSourceConnector); their adapters keep the Connector suffix.
                    .orShould().haveSimpleNameEndingWith("Connector");

    @ArchTest
    static final ArchRule portsShouldBeNamedCorrectly =
            classes()
                    .that().resideInAPackage("..domain.port..")
                    .should().haveSimpleNameEndingWith("Port")
                    .orShould().haveSimpleNameEndingWith("UseCase")
                    .orShould().haveSimpleNameEndingWith("Connector");

    @ArchTest
    static final ArchRule applicationServicesShouldBeNamedCorrectly =
            classes()
                    .that().resideInAPackage("..application.service..")
                    .and().areTopLevelClasses()
                    .should().haveSimpleNameEndingWith("Service");
}
