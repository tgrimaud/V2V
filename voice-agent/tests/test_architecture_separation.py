"""Enforce the STT/TTS separation contract (TASK-WEB-002, ST-7).

The voice-in (`stt_validation`) and voice-out (`tts_synthesis`) halves must stay
independently upgradeable and testable: neither may import the other. Shared
cross-cutting code lives in the neutral `voice_common/` package, which both may
import. This test parses every module in each package and fails on any direct or
transitive top-level import that crosses the boundary.
"""

import ast
import sys
import unittest
from pathlib import Path

VOICE_AGENT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(VOICE_AGENT_ROOT))

STT_PACKAGE = "stt_validation"
TTS_PACKAGE = "tts_synthesis"
SHARED_PACKAGE = "voice_common"
WEB_VOICE_PACKAGE = "web_voice"
CONVERSATION_PACKAGE = "conversation_backend"

PIPELINE_STT_SERVICE = VOICE_AGENT_ROOT / "voice_pipeline" / "stt_service.py"
PIPELINE_TTS_SERVICE = VOICE_AGENT_ROOT / "voice_pipeline" / "tts_service.py"
PIPELINE_ECHO = VOICE_AGENT_ROOT / "voice_pipeline" / "echo.py"


def _imported_modules(source: str) -> set[str]:
    """Absolute module names imported by a source file (relative imports excluded)."""
    tree = ast.parse(source)
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            # level > 0 is a relative import, which stays inside the same package.
            if node.level == 0 and node.module:
                modules.add(node.module)
    return modules


def _file_crossings(path: Path, forbidden_prefix: str) -> set[str]:
    """Top-level absolute imports in one file that reach into a forbidden package."""
    imported = _imported_modules(path.read_text(encoding="utf-8"))
    return {
        name
        for name in imported
        if name == forbidden_prefix or name.startswith(forbidden_prefix + ".")
    }


def _forbidden_imports(package: str, forbidden_prefix: str) -> dict[str, set[str]]:
    package_dir = VOICE_AGENT_ROOT / package
    offenders: dict[str, set[str]] = {}
    for path in package_dir.rglob("*.py"):
        imported = _imported_modules(path.read_text(encoding="utf-8"))
        crossing = {
            name
            for name in imported
            if name == forbidden_prefix or name.startswith(forbidden_prefix + ".")
        }
        if crossing:
            offenders[str(path.relative_to(VOICE_AGENT_ROOT))] = crossing
    return offenders


class ArchitectureSeparationTest(unittest.TestCase):
    def test_tts_never_imports_stt(self) -> None:
        # GIVEN the voice-out package
        # WHEN its imports are inspected
        offenders = _forbidden_imports(TTS_PACKAGE, STT_PACKAGE)
        # THEN nothing reaches into the voice-in package
        self.assertEqual(offenders, {}, f"tts_synthesis must not import stt_validation: {offenders}")

    def test_stt_never_imports_tts(self) -> None:
        # GIVEN the voice-in package
        # WHEN its imports are inspected
        offenders = _forbidden_imports(STT_PACKAGE, TTS_PACKAGE)
        # THEN nothing reaches into the voice-out package
        self.assertEqual(offenders, {}, f"stt_validation must not import tts_synthesis: {offenders}")

    def test_shared_package_stays_neutral(self) -> None:
        # GIVEN the neutral shared package
        # WHEN its imports are inspected against both halves
        stt_offenders = _forbidden_imports(SHARED_PACKAGE, STT_PACKAGE)
        tts_offenders = _forbidden_imports(SHARED_PACKAGE, TTS_PACKAGE)
        # THEN voice_common depends on neither half (or the boundary is circular)
        self.assertEqual(stt_offenders, {}, f"voice_common must not import stt_validation: {stt_offenders}")
        self.assertEqual(tts_offenders, {}, f"voice_common must not import tts_synthesis: {tts_offenders}")

    def test_detector_flags_a_synthetic_cross_import(self) -> None:
        # GIVEN a source file that crosses the boundary (guards against a broken test)
        source = "from stt_validation.telemetry import TelemetryRecorder\nimport tts_synthesis.runner\n"
        # WHEN inspected for either forbidden prefix
        imported = _imported_modules(source)
        # THEN both cross-package imports are detected
        self.assertIn("stt_validation.telemetry", imported)
        self.assertIn("tts_synthesis.runner", imported)

    def test_pipeline_stt_service_never_imports_tts(self) -> None:
        # GIVEN the Pipecat STT service (TASK-WEB-005)
        # WHEN its imports are inspected
        # THEN it never reaches into the voice-out package
        self.assertEqual(_file_crossings(PIPELINE_STT_SERVICE, TTS_PACKAGE), set())

    def test_pipeline_tts_service_never_imports_stt(self) -> None:
        # GIVEN the Pipecat TTS service (TASK-WEB-005)
        # WHEN its imports are inspected
        # THEN it never reaches into the voice-in package
        self.assertEqual(_file_crossings(PIPELINE_TTS_SERVICE, STT_PACKAGE), set())

    def test_pipeline_services_do_not_import_web_voice(self) -> None:
        # GIVEN the Pipecat STT/TTS services (injection keeps them transport-agnostic)
        # WHEN their imports are inspected
        # THEN neither pulls the web_voice package (whose init drags BOTH halves in)
        self.assertEqual(_file_crossings(PIPELINE_STT_SERVICE, WEB_VOICE_PACKAGE), set())
        self.assertEqual(_file_crossings(PIPELINE_TTS_SERVICE, WEB_VOICE_PACKAGE), set())

    def test_pipeline_echo_stays_domain_neutral(self) -> None:
        # GIVEN the echo processor (TASK-WEB-005)
        # WHEN its imports are inspected
        # THEN it depends on neither voice half
        self.assertEqual(_file_crossings(PIPELINE_ECHO, STT_PACKAGE), set())
        self.assertEqual(_file_crossings(PIPELINE_ECHO, TTS_PACKAGE), set())

    def test_conversation_backend_stays_neutral(self) -> None:
        # GIVEN the conversation backend seam (TASK-WEB-003), the neutral STT↔TTS middle
        # WHEN its imports are inspected against both halves and the web transport
        stt_offenders = _forbidden_imports(CONVERSATION_PACKAGE, STT_PACKAGE)
        tts_offenders = _forbidden_imports(CONVERSATION_PACKAGE, TTS_PACKAGE)
        web_offenders = _forbidden_imports(CONVERSATION_PACKAGE, WEB_VOICE_PACKAGE)
        # THEN it depends on none of them (it may only import the neutral voice_common)
        self.assertEqual(stt_offenders, {}, f"conversation_backend must not import stt_validation: {stt_offenders}")
        self.assertEqual(tts_offenders, {}, f"conversation_backend must not import tts_synthesis: {tts_offenders}")
        self.assertEqual(web_offenders, {}, f"conversation_backend must not import web_voice: {web_offenders}")

    def test_relative_imports_are_not_flagged_as_cross_package(self) -> None:
        # GIVEN in-package relative imports and a shared voice_common import
        source = "from .models import TtsOutcome\nfrom voice_common.telemetry import TelemetryRecorder\n"
        # WHEN inspected
        imported = _imported_modules(source)
        # THEN no stt_validation / tts_synthesis absolute import appears
        self.assertNotIn("stt_validation", {m.split(".")[0] for m in imported})
        self.assertNotIn("tts_synthesis", {m.split(".")[0] for m in imported})


if __name__ == "__main__":
    unittest.main()
