import asyncio
import sys
from pathlib import Path

VOICE_AGENT_ROOT = Path(__file__).resolve().parents[1]
if str(VOICE_AGENT_ROOT) not in sys.path:
    sys.path.insert(0, str(VOICE_AGENT_ROOT))


def before_scenario(context, scenario):  # noqa: ARG001 - behave hook signature
    context.manifest = None
    context.report = None
    context.failure_result = None
    context.server_loop = None
    context.server_runner = None


def after_scenario(context, scenario):  # noqa: ARG001 - behave hook signature
    # Tear down the aiohttp test server started by "the web voice runtime server is running"
    # (ADR-0053 / TASK-WEB-048 Phase 2 replaced the retired stdlib ThreadingHTTPServer).
    loop = getattr(context, "server_loop", None)
    runner = getattr(context, "server_runner", None)
    if loop is not None:
        if runner is not None:
            future = asyncio.run_coroutine_threadsafe(runner.cleanup(), loop)
            try:
                future.result(timeout=5)
            except Exception:  # noqa: BLE001 - best-effort teardown
                pass
        loop.call_soon_threadsafe(loop.stop)
        context.server_loop = None
        context.server_runner = None
