# Flo - story template (Product / Business)

**Agent:** Flo (`product-business`)  
**Usage:** copy this block for each story; replace the `{{...}}` placeholders.

**Story shape** - check one.

| Story shape | Check |
|-------------|-------|
| Front only | [ ] |
| Back only | [ ] |
| Full stack (front + back) | [ ] |

---

### Story {{epic_num}}.{{story_num}}: {{story_title}}

### User story

As a {{user_type_or_segment}},  
I want {{capability_in_stakeholder_language}},  
So that {{observable_benefit_or_job_done}}.

### Context

**Situation**  
{{where_this_sits_in_the_product_who_is_affected_current_behavior}}

**Implementation setting**  
{{where_this_must_be_delivered_surfaces_journeys_integrations_constraints_no_stack_prescription_unless_product_owned}}

**Problem to solve**  
{{the_gap_pain_risk_or_opportunity_this_feature_addresses}}

**Value / outcome (short)**  
{{one_or_two_sentences_user_and_org_value}}

**In scope**
- {{included_behavior_or_slice_1}}
- {{included_behavior_or_slice_2}}

**Out of scope**
- {{explicit_exclusion_1}}
- {{explicit_exclusion_2}}

---

### Business context

**Personas**

| Persona | Description |
|---------|-------------|
| {{persona_name}} | {{who_they_are_what_they_need_segment}} |

**Pain points**
- {{current_pain_or_friction_this_story_addresses}}

**Business value**  
{{why_this_matters_to_the_organization_revenue_retention_compliance_cost_reduction_risk_mitigation}}

---

### Permissions & roles

Who may use this capability and under which conditions.

| Role / segment | Permission | Preconditions |
|----------------|------------|---------------|
| {{role_1}} | {{permission_description}} | {{preconditions_or_dash}} |

**Denied / forbidden cases**
- {{what_non_authorized_users_must_not_be_able_to_do_observable}}

---

### Business rules

Rules are acceptance-grade and feed acceptance criteria scenarios. Use stable
IDs (`BR-1`, `BR-2`, ...).

#### Shared

| ID | Rule |
|----|------|
| BR-1 | {{rule_applying_to_the_story}} |
| BR-2 | {{another_rule}} |

#### Front-specific

| ID | Rule |
|----|------|
| BR-F1 | {{front_only_rule}} |

#### Back-specific

| ID | Rule |
|----|------|
| BR-B1 | {{back_only_rule}} |

**Constraints to follow**  
{{product_level_compliance_limits_audit_retention_or_policy_constraints}}

---

### Degraded / error states

| Trigger | Expected product behavior |
|---------|---------------------------|
| {{trigger}} | {{what_the_user_sees_or_what_the_system_preserves}} |

---

### Acceptance criteria (Gherkin)

Write explicit `Scenario:` titles. Reference business rule IDs in a trailing
comment line.

```gherkin
Feature: {{short_feature_name_for_this_story}}

  Scenario: {{concise_title_outcome_or_situation}}
    Given {{precondition}}
    When {{action}}
    Then {{expected_outcome}}
    And {{optional_step}}
    # BR: BR-1, BR-2
```

Add scenarios until every must rule is covered or explicitly deferred.

---

### Traceability

Every business rule must map to at least one Gherkin scenario, and every
scenario must reference at least one BR.

| BR ID | Scenario(s) covering it | Covered? |
|-------|-------------------------|----------|
| BR-1 | {{Scenario_title}} | yes |

---

### Analytics / tracking requirements

Flo defines what to track; instrumentation details belong to Engineering.

| Event / metric | Trigger | Purpose |
|----------------|---------|---------|
| {{event_or_metric}} | {{user_action_or_state}} | {{why_it_matters}} |

---

### Accessibility requirements

- **Target level:** {{WCAG_2.2_AA_or_other_standard}}
- **Key expectations:**
  - {{product_owned_accessibility_expectation}}

---

### Relevant product constraints

- {{compliance_theme_performance_expectation_data_residency_or_policy}}

### Risks, premises, or sensitive topics

- {{premise_with_attribution_or_empty}}

### Potential breaking change

- [ ] No known consumer / contract / baseline impact
- [ ] **BREAKING** - describe: {{what_breaks_for_whom_migration_expectation_at_product_level}} - escalation / recorded review: {{owner_or_link}}

### Dependencies

**Blocked by**

| Dependency | Why it blocks | Owner / status |
|------------|---------------|----------------|
| {{dependency}} | {{what_this_story_needs_from_it}} | {{owner_or_dash}} |

**Blocks**

| Dependent | What it needs from this story |
|-----------|-------------------------------|
| {{dependent}} | {{what_it_consumes_or_depends_on}} |

**External dependencies**

- {{external_dependency_and_current_status}}

### Open questions / blockers

| Topic | Impact if unresolved | Decision owner | Due |
|-------|----------------------|----------------|-----|
| {{unknown_1}} | {{why_it_matters}} | {{decision_owner}} | {{date_or_dash}} |

### Decisions / log

- {{link_or_one_line_to_decision_log_if_any}}

---

## Notes

- Product stories describe intent, value, business rules and acceptance.
- Do not include API paths, HTTP codes, headers, table names, event names, queues, frameworks or deployment details unless Architecture has baselined them as product-visible contracts.
- Rules and scenarios must stay verifiable in product-observable language.
- Material ambiguity becomes an open question or escalation, not a hidden assumption.
