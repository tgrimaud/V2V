"""Minimal channel envelope for a web voice turn.

This is the direction described in docs/architecture/channel-identity-boundary.md
(Minimum Channel Envelope). TASK-WEB-001 only needs the fields that make the turn
traceable end to end; identity confidence and reply mode are added by later
slices (governed by OQ-001 / TASK-WEB-003).
"""

from dataclasses import dataclass
from uuid import uuid4

WEB_VOICE_CHANNEL = "web_voice"
# Genesys Audio Connector media plane (TASK-WEB-041, ADR-0049/0009). One more channel
# behind the normalized envelope; the backend stays the conversation brain (ADR-0001).
GENESYS_AUDIO_CONNECTOR_CHANNEL = "genesys_audio_connector"


@dataclass(frozen=True)
class ChannelEnvelope:
    channel: str
    conversation_id: str
    external_session_id: str
    message_id: str
    correlation_id: str
    # US-042: optional UI-selected language ("fr"/"en") carried through the turn so the
    # backend can force the answer language. None keeps backend auto-detection.
    language: str | None = None

    @classmethod
    def for_web_turn(
        cls,
        conversation_id: str | None = None,
        external_session_id: str | None = None,
        correlation_id: str | None = None,
        language: str | None = None,
    ) -> "ChannelEnvelope":
        return cls(
            channel=WEB_VOICE_CHANNEL,
            conversation_id=conversation_id or str(uuid4()),
            external_session_id=external_session_id or str(uuid4()),
            message_id=str(uuid4()),
            correlation_id=correlation_id or str(uuid4()),
            language=language or None,
        )

    @classmethod
    def for_genesys_turn(
        cls,
        conversation_id: str | None = None,
        external_session_id: str | None = None,
        correlation_id: str | None = None,
        language: str | None = None,
    ) -> "ChannelEnvelope":
        """Envelope for a Genesys Audio Connector call (TASK-WEB-041).

        The Genesys ``conversationId`` is carried as both the conversation id and the
        correlation id (unless overridden) so a single deterministic ``traceparent``
        stitches the Genesys leg, the runtime and the backend into one trace.
        """
        conversation = conversation_id or str(uuid4())
        return cls(
            channel=GENESYS_AUDIO_CONNECTOR_CHANNEL,
            conversation_id=conversation,
            external_session_id=external_session_id or conversation,
            message_id=str(uuid4()),
            correlation_id=correlation_id or conversation,
            language=language or None,
        )

    def as_attributes(self) -> dict[str, str]:
        attributes = {
            "channel": self.channel,
            "conversation_id": self.conversation_id,
            "external_session_id": self.external_session_id,
            "message_id": self.message_id,
            "correlation_id": self.correlation_id,
        }
        if self.language:
            attributes["language"] = self.language
        return attributes
