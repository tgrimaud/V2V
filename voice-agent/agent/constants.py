"""Shared constants for the voice agent (single source of truth).

Keeping these here avoids drift between the custom bridge (strategy A,
`bridge_server.py`) and the Pipecat bot (strategy B, `bot.py`), which both
speak the same scripted welcome at connection.
"""

WELCOME_MESSAGE = (
    "Bonjour ! Je suis votre assistant virtuel du support télécom. "
    "Comment puis-je vous aider aujourd'hui ?"
)
