#!/usr/bin/env python3
"""Generate the controlled STT fixtures as raw PCM16 mono 16 kHz (TASK-STT-007).

macOS-only: uses the built-in `say` engine. Produces one sample per declared
category, matching the references in `manifest.json`.

Output is **raw PCM** (no WAV header) on purpose: the Gradium provider sends the
file bytes with `input_format=pcm_16000` / `Content-Type: audio/pcm`, so a WAV
container header would be read as leading samples (a click). Raw PCM is the native
Gradium input. The deterministic `FixtureSttProvider` ignores the audio bytes (it
reads the `.txt` sidecar), so both provider paths work with these files.

Note: `say` speech is clean/synthetic. `noisy` mixes synthetic white noise and
`accented` uses a Canadian-French voice (fr_CA) against the fr_FR others — these
are proxies, not real-world recordings. Replace with real captures to make
per-category quality representative (rest of TASK-STT-007).
"""

import array
import random
import subprocess
import tempfile
import wave
from pathlib import Path

SAMPLE_RATE = 16000
FIXTURES_DIR = Path(__file__).resolve().parent

# (relative output, say voice, spoken text, add_noise)
SPECS = [
    ("short/greeting.pcm", "Thomas", "Bonjour.", False),
    (
        "long/billing-question.pcm",
        "Thomas",
        "Pourquoi ma facture de téléphone est plus élevée que le mois dernier ?",
        False,
    ),
    (
        "noisy/noisy-question.pcm",
        "Jacques",
        "Je voudrais comprendre le montant de ma dernière facture mensuelle.",
        True,
    ),
    (
        "accented/accented-question.pcm",
        "Amélie",  # fr_CA — a genuine accent difference vs the fr_FR voices
        "Est-ce que je peux payer ma facture en plusieurs fois ?",
        False,
    ),
]


def say_to_pcm(voice: str, text: str) -> bytes:
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        wav_path = Path(tmp.name)
    try:
        subprocess.run(
            ["say", "-v", voice, "-o", str(wav_path),
             "--data-format=LEI16@16000", "--file-format=WAVE", text],
            check=True,
        )
        with wave.open(str(wav_path), "rb") as wav:
            assert wav.getframerate() == SAMPLE_RATE, wav.getframerate()
            assert wav.getnchannels() == 1, wav.getnchannels()
            assert wav.getsampwidth() == 2, wav.getsampwidth()
            return wav.readframes(wav.getnframes())
    finally:
        wav_path.unlink(missing_ok=True)


def mix_white_noise(pcm: bytes, amplitude: float = 0.06, seed: int = 42) -> bytes:
    samples = array.array("h")
    samples.frombytes(pcm)
    peak = 32767
    noise = int(amplitude * peak)
    rng = random.Random(seed)
    for i in range(len(samples)):
        value = samples[i] + rng.randint(-noise, noise)
        samples[i] = max(-peak, min(peak, value))
    return samples.tobytes()


def main() -> None:
    for rel, voice, text, noisy in SPECS:
        pcm = say_to_pcm(voice, text)
        if noisy:
            pcm = mix_white_noise(pcm)
        out = FIXTURES_DIR / rel
        out.write_bytes(pcm)
        print(f"{rel}: {len(pcm)} bytes ({len(pcm) / 2 / SAMPLE_RATE:.2f}s, voice={voice})")

    silence = FIXTURES_DIR / "silence/silence.pcm"
    silence.write_bytes(b"\x00\x00" * SAMPLE_RATE)  # 1.0 s of digital silence
    print(f"silence/silence.pcm: {SAMPLE_RATE * 2} bytes (1.00s, generated)")


if __name__ == "__main__":
    main()
