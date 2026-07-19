package com.voicesupport.architecture;

import com.tngtech.archunit.core.importer.ImportOption;
import com.tngtech.archunit.junit.AnalyzeClasses;
import com.tngtech.archunit.junit.ArchTest;
import com.tngtech.archunit.lang.ArchRule;

import static com.tngtech.archunit.lang.syntax.ArchRuleDefinition.classes;
import static com.tngtech.archunit.lang.syntax.ArchRuleDefinition.noClasses;

// Enforces the ADR-0027 boundary between the `knowledge` and `conversation` bounded contexts.
// Contexts are top-level packages, so rules use absolute prefixes: the loose "..knowledge.."
// pattern would also match the seam sub-package `conversation...adapter.out.knowledge`.
@AnalyzeClasses(packages = "com.voicesupport", importOptions = ImportOption.DoNotIncludeTests.class)
class ContextBoundaryTest {

    private static final String KNOWLEDGE = "com.voicesupport.knowledge..";
    private static final String CONVERSATION = "com.voicesupport.conversation..";
    private static final String SEAM = "com.voicesupport.conversation.infrastructure.adapter.out.knowledge..";

    @ArchTest
    static final ArchRule conversationDomainMustNotDependOnKnowledge =
            noClasses()
                    .that().resideInAPackage("com.voicesupport.conversation.domain..")
                    .should().dependOnClassesThat().resideInAPackage(KNOWLEDGE);

    @ArchTest
    static final ArchRule knowledgeMustNotDependOnConversation =
            noClasses()
                    .that().resideInAPackage(KNOWLEDGE)
                    .should().dependOnClassesThat().resideInAPackage(CONVERSATION);

    @ArchTest
    static final ArchRule onlyTheSeamMayBridgeConversationToKnowledge =
            noClasses()
                    .that().resideInAPackage(CONVERSATION)
                    .and().resideOutsideOfPackage(SEAM)
                    .should().dependOnClassesThat().resideInAPackage(KNOWLEDGE);

    @ArchTest
    static final ArchRule seamMayOnlyReachKnowledgePublishedApi =
            classes()
                    .that().resideInAPackage(SEAM)
                    .should().onlyDependOnClassesThat()
                    .resideInAnyPackage(
                            CONVERSATION,
                            "com.voicesupport.knowledge.domain.port.in..",
                            "com.voicesupport.knowledge.domain.model..",
                            // Cross-cutting, context-agnostic shared utilities (e.g. observability)
                            // are allowed like Spring/JDK; `sharedMustNotDependOnAnyContext` keeps
                            // `shared` from ever depending back on a bounded context.
                            "com.voicesupport.shared..",
                            "java..",
                            "jakarta..",
                            "org.springframework..");

    @ArchTest
    static final ArchRule sharedMustNotDependOnAnyContext =
            noClasses()
                    .that().resideInAPackage("com.voicesupport.shared..")
                    .should().dependOnClassesThat()
                    .resideInAnyPackage(KNOWLEDGE, CONVERSATION);
}
