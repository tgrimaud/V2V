#!/usr/bin/env python3
"""Generate the controlled STT fixtures as raw PCM16 mono 16 kHz (TASK-STT-007).

macOS-only: uses the built-in `say` engine. Produces **multiple samples per
declared category** (varied voices and phrasings) plus silence clips, matching the
references in `manifest.json`.

Output is **raw PCM** (no WAV header) on purpose: the Gradium provider sends the
file bytes with `input_format=pcm_16000` / `Content-Type: audio/pcm`, so a WAV
container header would be read as leading samples (a click). Raw PCM is the native
Gradium input. The deterministic `FixtureSttProvider` ignores the audio bytes (it
reads the `.txt` sidecar), so both provider paths work with these files.

Honesty note: `say` speech is clean/synthetic. `noisy` mixes synthetic white noise
and `accented` uses Canadian-French voices (fr_CA) against the fr_FR others — these
are proxies, not real-world recordings. Real human captures (especially for `noisy`
and `accented`) remain the highest-value follow-up for statistical significance.
"""

import array
import random
import subprocess
import tempfile
import wave
from dataclasses import dataclass
from pathlib import Path

SAMPLE_RATE = 16000
FIXTURES_DIR = Path(__file__).resolve().parent

# `say` starts speaking on the very first sample; Gradium's endpointing then clips
# the first word ("Merci beaucoup" -> "beaucoup"). Pad every clip with a short
# lead-in / lead-out of silence so the onset is clean and the first word survives.
LEAD_SILENCE_MS = 300
TRAIL_SILENCE_MS = 200


@dataclass(frozen=True)
class SpokenSpec:
    category: str
    slug: str
    voice: str
    text: str
    noisy: bool = False

    @property
    def rel_path(self) -> str:
        return f"{self.category}/{self.slug}.pcm"


# Multiple samples per usable category. Voices are varied within a category so the
# fixtures are not a single synthetic timbre; the text mirrors the manifest
# `reference` for each fixture (normalization makes case/punctuation/accents moot).
SPOKEN_SPECS = [
    # short — a few words each
    SpokenSpec("short", "greeting", "Thomas", "Bonjour."),
    SpokenSpec("short", "thanks", "Jacques", "Merci beaucoup."),
    SpokenSpec("short", "goodbye", "Flo (French (France))", "Au revoir et bonne journée."),
    SpokenSpec("short", "question", "Sandy (French (France))", "J'ai une question."),
    SpokenSpec("short", "urgent", "Rocko (French (France))", "C'est assez urgent."),
    # long — full support/billing sentences
    SpokenSpec(
        "long", "billing-question", "Thomas",
        "Pourquoi ma facture de téléphone est plus élevée que le mois dernier ?",
    ),
    SpokenSpec(
        "long", "extra-fees", "Jacques",
        "Je souhaite comprendre pourquoi des frais supplémentaires apparaissent sur mon relevé ce mois.",
    ),
    SpokenSpec(
        "long", "invoice-breakdown", "Eddy (French (France))",
        "Pouvez-vous m'expliquer en détail les différentes lignes qui composent le montant total de ma facture ?",
    ),
    SpokenSpec(
        "long", "cancel-subscription", "Flo (French (France))",
        "J'aimerais savoir comment résilier mon abonnement et connaître les frais de résiliation associés.",
    ),
    SpokenSpec(
        "long", "payment-plan", "Sandy (French (France))",
        "Serait-il possible de mettre en place un échéancier pour étaler le paiement de ma facture ?",
    ),
    # noisy — clean speech mixed with synthetic white noise
    SpokenSpec(
        "noisy", "monthly-amount", "Jacques",
        "Je voudrais comprendre le montant de ma dernière facture mensuelle.", True,
    ),
    SpokenSpec(
        "noisy", "slow-internet", "Thomas",
        "Ma connexion internet est très lente depuis plusieurs jours.", True,
    ),
    SpokenSpec(
        "noisy", "no-sms", "Flo (French (France))",
        "Je n'arrive plus à envoyer des messages depuis ce matin.", True,
    ),
    SpokenSpec(
        "noisy", "plan-changed", "Rocko (French (France))",
        "Mon forfait mobile a été modifié sans mon accord.", True,
    ),
    SpokenSpec(
        "noisy", "landline-issue", "Sandy (French (France))",
        "Je souhaite signaler un problème sur ma ligne fixe.", True,
    ),
    # accented — Canadian-French voices (fr_CA)
    SpokenSpec(
        "accented", "installments", "Amélie",
        "Est-ce que je peux payer ma facture en plusieurs fois ?",
    ),
    SpokenSpec(
        "accented", "cheaper-plan", "Eddy (French (Canada))",
        "J'aimerais changer mon forfait pour un plan moins cher.",
    ),
    SpokenSpec(
        "accented", "check-balance", "Flo (French (Canada))",
        "Pouvez-vous vérifier mon solde s'il vous plaît ?",
    ),
    SpokenSpec(
        "accented", "too-high", "Reed (French (Canada))",
        "Ma facture me semble beaucoup trop élevée ce mois-ci.",
    ),
    SpokenSpec(
        "accented", "add-option", "Sandy (French (Canada))",
        "Je veux ajouter une option à mon abonnement.",
    ),
]

# (relative output, silence duration in seconds)
SILENCE_SPECS = [
    ("silence/silence.pcm", 1.0),
    ("silence/silence-long.pcm", 1.5),
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


def pad_silence(pcm: bytes, lead_ms: int, trail_ms: int) -> bytes:
    lead = b"\x00\x00" * int(SAMPLE_RATE * lead_ms / 1000)
    trail = b"\x00\x00" * int(SAMPLE_RATE * trail_ms / 1000)
    return lead + pcm + trail


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
    for index, spec in enumerate(SPOKEN_SPECS):
        pcm = pad_silence(say_to_pcm(spec.voice, spec.text), LEAD_SILENCE_MS, TRAIL_SILENCE_MS)
        if spec.noisy:
            pcm = mix_white_noise(pcm, seed=1000 + index)
        out = FIXTURES_DIR / spec.rel_path
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(pcm)
        # Sidecar consumed by the deterministic FixtureSttProvider (offline path).
        out.with_suffix(".txt").write_text(spec.text, encoding="utf-8")
        print(f"{spec.rel_path}: {len(pcm)} bytes "
              f"({len(pcm) / 2 / SAMPLE_RATE:.2f}s, voice={spec.voice})")

    for rel, seconds in SILENCE_SPECS:
        out = FIXTURES_DIR / rel
        out.parent.mkdir(parents=True, exist_ok=True)
        frames = int(SAMPLE_RATE * seconds)
        out.write_bytes(b"\x00\x00" * frames)
        # Blank sidecar => FixtureSttProvider raises => outcome "failed", nothing invented.
        out.with_suffix(".txt").write_text("   ", encoding="utf-8")
        print(f"{rel}: {frames * 2} bytes ({seconds:.2f}s, generated)")


if __name__ == "__main__":
    main()
