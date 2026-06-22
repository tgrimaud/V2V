"""Tests for the server-side turn detector (endpointing)."""

from agent.turn_detector import (
    SAMPLE_RATE,
    SAMPLE_WIDTH,
    TurnDetector,
    TurnDetectorConfig,
    frame_rms,
)


def _silence(ms: int) -> bytes:
    samples = int(SAMPLE_RATE * ms / 1000)
    return b"\x00\x00" * samples


def _speech(ms: int, amplitude: int = 8000) -> bytes:
    """Synthetic high-amplitude PCM (alternating +/- amplitude)."""
    samples = int(SAMPLE_RATE * ms / 1000)
    hi = amplitude.to_bytes(2, "little", signed=True)
    lo = (-amplitude).to_bytes(2, "little", signed=True)
    return (hi + lo) * (samples // 2)


def test_frame_rms_is_zero_for_silence():
    # GIVEN a silent frame
    # WHEN computing RMS
    # THEN it is zero
    assert frame_rms(_silence(20)) == 0.0


def test_frame_rms_is_high_for_speech():
    # GIVEN a loud frame
    # WHEN computing RMS
    # THEN it is close to the amplitude
    assert frame_rms(_speech(20, amplitude=8000)) > 5000


def test_no_end_of_turn_on_silence_only():
    # GIVEN only silence
    detector = TurnDetector()
    # WHEN processed
    ended = detector.process(_silence(2000))
    # THEN no turn ends and no speech was detected
    assert ended is False
    assert detector.has_speech is False


def test_end_of_turn_after_speech_then_silence():
    # GIVEN speech followed by enough trailing silence
    detector = TurnDetector(TurnDetectorConfig(silence_ms=500, min_speech_ms=200))
    # WHEN speech is fed (no end yet)
    assert detector.process(_speech(400)) is False
    assert detector.has_speech is True
    # THEN end-of-turn triggers once silence threshold is crossed
    assert detector.process(_silence(500)) is True


def test_short_speech_does_not_end_turn():
    # GIVEN speech shorter than min_speech_ms
    detector = TurnDetector(TurnDetectorConfig(silence_ms=300, min_speech_ms=400))
    detector.process(_speech(100))
    # WHEN followed by silence
    ended = detector.process(_silence(1000))
    # THEN the turn does not end (not enough speech)
    assert ended is False


def test_silence_resets_between_speech_segments():
    # GIVEN speech, a short pause shorter than silence_ms, then more speech
    detector = TurnDetector(TurnDetectorConfig(silence_ms=500, min_speech_ms=200))
    assert detector.process(_speech(300)) is False
    assert detector.process(_silence(300)) is False  # pause too short
    assert detector.process(_speech(300)) is False    # speech resumes, resets silence
    # THEN only a full trailing silence ends the turn
    assert detector.process(_silence(500)) is True


def test_process_after_end_returns_false():
    # GIVEN a detector that already ended a turn
    detector = TurnDetector(TurnDetectorConfig(silence_ms=200, min_speech_ms=100))
    detector.process(_speech(200))
    assert detector.process(_silence(200)) is True
    # WHEN more audio is fed without reset
    # THEN it stays ended
    assert detector.process(_speech(500)) is False


def test_reset_allows_new_turn():
    # GIVEN a detector that ended a turn
    detector = TurnDetector(TurnDetectorConfig(silence_ms=200, min_speech_ms=100))
    detector.process(_speech(200))
    detector.process(_silence(200))
    # WHEN reset
    detector.reset()
    # THEN a new turn can be detected
    assert detector.has_speech is False
    assert detector.process(_speech(200)) is False
    assert detector.process(_silence(200)) is True


def test_handles_chunks_smaller_than_frame():
    # GIVEN audio fed in tiny chunks not aligned to frame size
    detector = TurnDetector(TurnDetectorConfig(silence_ms=400, min_speech_ms=200, frame_ms=20))
    speech = _speech(400)
    for i in range(0, len(speech), 7):  # odd-sized chunks
        detector.process(speech[i:i + 7])
    # WHEN trailing silence is fed in tiny chunks
    silence = _silence(400)
    ended = False
    for i in range(0, len(silence), 5):
        ended = detector.process(silence[i:i + 5]) or ended
    # THEN end-of-turn is still detected
    assert ended is True
