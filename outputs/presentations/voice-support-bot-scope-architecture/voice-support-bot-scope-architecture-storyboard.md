# Voice Support Bot - V1 Scope And First Architecture Vision

Concise storyboard aligned with the readable PPTX deck.

- Readable PPTX deck: `outputs/presentations/voice-support-bot-scope-architecture/voice-support-bot-scope-architecture.pptx`
- Format: 8 slides, one idea per slide, simplified architecture diagrams.

## Slide 1 - Voice Support Bot

**Key message**: V1 scope and first architecture vision

- Voice assistant for explaining telecom invoice discrepancies.

## Slide 2 - V1 answers a simple customer question

**Key message**: Why did my invoice increase?

- Compare two billing periods.
- Return a clear, traceable voice explanation.

## Slide 3 - The first scope is deliberately focused

**Key message**: Invoice explanation before a general support chatbot

- Channels: phone and web voice chat.
- Value: explain deltas using BSS-backed evidence.

## Slide 4 - AI formulates, the engine calculates

**Key message**: Reliability before fluency

- The BSS remains the source of truth.
- The LLM never calculates invoice amounts from PDFs.

## Slide 5 - Target voice architecture

**Key message**: Real-time voice path separated from business reasoning

- Diagram: Web/phone -> Pipecat + Gradium -> Java backend -> BSS/RAG/Mistral -> voice answer.

## Slide 6 - Billing explanation flow

**Key message**: Deterministic comparison before response generation

- Diagram: billing-api -> invoice PDF -> extracted JSON -> deterministic comparison -> LLM wording.

## Slide 7 - Platform choices keep the system extensible

**Key message**: Billing is the first domain, not the product boundary

- Java owns RAG, comparison, and evidence handling.
- Providers for LLM, STT, and TTS stay configurable.

## Slide 8 - Validate the Galaxion contract next

**Key message**: Secure the data contract before industrialization

- Collect anonymized invoices and linked metadata.
- Build a compatible BSS mock, then one end-to-end scenario.
