"""Tests for the Twilio Media Streams telephony protocol helpers."""

import base64
import json

from agent.telephony import (
    MediaStreamEvent,
    build_clear_message,
    build_media_message,
    parse_twilio_message,
    telephony_turn_detector,
)


def test_parse_start_event_extracts_stream_sid():
    raw = json.dumps({"event": "start", "start": {"streamSid": "MZ123"}})
    event = parse_twilio_message(raw)
    assert event.kind == "start"
    assert event.stream_sid == "MZ123"


def test_parse_media_event_decodes_base64_mulaw():
    payload = base64.b64encode(b"\xff\xfe\xfd").decode("ascii")
    raw = json.dumps({"event": "media", "media": {"payload": payload}})
    event = parse_twilio_message(raw)
    assert event.kind == "media"
    assert event.mulaw == b"\xff\xfe\xfd"


def test_parse_stop_event():
    event = parse_twilio_message(json.dumps({"event": "stop"}))
    assert event.kind == "stop"


def test_parse_invalid_json_returns_unknown():
    assert parse_twilio_message("not json").kind == "unknown"


def test_parse_unknown_event():
    assert parse_twilio_message(json.dumps({"event": "dtmf"})).kind == "unknown"


def test_build_media_message_roundtrips_audio():
    msg = build_media_message("MZ1", b"\x01\x02\x03")
    data = json.loads(msg)
    assert data["event"] == "media"
    assert data["streamSid"] == "MZ1"
    assert base64.b64decode(data["media"]["payload"]) == b"\x01\x02\x03"


def test_build_clear_message():
    data = json.loads(build_clear_message("MZ1"))
    assert data == {"event": "clear", "streamSid": "MZ1"}


def test_telephony_turn_detector_uses_8khz():
    detector = telephony_turn_detector()
    assert detector.config.sample_rate == 8000


def test_media_stream_event_defaults():
    event = MediaStreamEvent("connected")
    assert event.stream_sid is None
    assert event.mulaw is None
