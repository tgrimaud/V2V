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
