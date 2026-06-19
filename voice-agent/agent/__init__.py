"""Pipecat voice agent for Telecom support.

Orchestrates the real-time voice pipeline:
  Browser/Twilio audio → Gradium STT → Java backend (RAG) → Gradium TTS → audio out

The Java backend handles RAG retrieval, LLM generation, and escalation detection.
This agent handles the real-time voice orchestration via Pipecat + Gradium.
"""
