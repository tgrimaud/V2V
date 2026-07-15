Feature: Voice journey timing by pipeline slice
  As a product owner
  I want to measure the voice journey by pipeline slice
  So that the team can identify where latency is introduced

  # US-036 - timings assessed separately with p50/p95/p99 over a reviewed sample
  Scenario: Voice journey timing is measurable by slice
    Given a reviewed sample of web voice turns captured on one recorder
    When the pipeline timing report is built for the sample
    Then channel ingress, end-of-turn, STT, backend, TTS first audio and channel egress are reported separately
    And the instrumented slices expose p50, p95 and p99 for the reviewed sample
    And the not-yet-instrumented slices are flagged as latency gaps to close

  # TASK-WEB-003-E / US-036 - the full answering loop measures every slice, backend included
  Scenario: The full answering loop measures every slice including backend
    Given a reviewed sample of full web voice turns through the backend bridge
    When the pipeline timing report is built for the sample
    Then the TTS first audio and channel egress slices expose p50, p95 and p99 for the reviewed sample
    And the backend slice is reported measured, no longer a latency gap
    And no implemented slice remains a latency gap to close

  # TASK-WEB-003-E / US-036 - one correlation id flows across the whole journey
  Scenario: The backend slice becomes measured with one correlation id end to end
    Given a full web voice turn through the backend bridge
    When the pipeline timing report is built for the sample
    Then the backend slice is reported measured, no longer a latency gap
    And every recorded slice shares one correlation id
