import sys
from pathlib import Path

VOICE_AGENT_ROOT = Path(__file__).resolve().parents[1]
if str(VOICE_AGENT_ROOT) not in sys.path:
    sys.path.insert(0, str(VOICE_AGENT_ROOT))


def before_scenario(context, scenario):  # noqa: ARG001 - behave hook signature
    context.manifest = None
    context.report = None
    context.failure_result = None
    context.http_server = None


def after_scenario(context, scenario):  # noqa: ARG001 - behave hook signature
    server = getattr(context, "http_server", None)
    if server is not None:
        server.shutdown()
        server.server_close()
        context.http_server = None
