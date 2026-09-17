package com.voicesupport.bdd;

import org.junit.platform.suite.api.ConfigurationParameter;
import org.junit.platform.suite.api.IncludeEngines;
import org.junit.platform.suite.api.SelectClasspathResource;
import org.junit.platform.suite.api.Suite;

import static io.cucumber.junit.platform.engine.Constants.GLUE_PROPERTY_NAME;

// BDD suite (TASK-BE-051 robustness): select the KNOWN feature files explicitly instead of the whole
// `features` classpath root. `@SelectClasspathResource("features")` used to scan target/test-classes,
// so a STALE gitignored artifact (e.g. a `features/billing-explanation.feature` copied by an earlier
// build but with no matching glue in com.voicesupport.bdd.steps) made `mvn test` (without `clean`) fail
// with undefined-step errors, while `mvn clean test` passed. Enumerating the features makes the run
// deterministic regardless of a dirty target/. When you add a new feature under
// src/test/resources/features/, add a line here (and its glue in com.voicesupport.bdd.steps).
@Suite
@IncludeEngines("cucumber")
@SelectClasspathResource("features/answer-concision.feature")
@SelectClasspathResource("features/answer-language.feature")
@SelectClasspathResource("features/answer-wording.feature")
@SelectClasspathResource("features/conversation-grounding.feature")
@SelectClasspathResource("features/conversation-memory.feature")
@SelectClasspathResource("features/csv-knowledge-ingestion.feature")
@SelectClasspathResource("features/knowledge-ingestion.feature")
@ConfigurationParameter(key = GLUE_PROPERTY_NAME, value = "com.voicesupport.bdd.steps")
public class RunKnowledgeBddTest {
}
