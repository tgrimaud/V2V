# Voice Support Bot - Python voice bridge image (TASK-DEPLOY-002, ADR-0038).
# Single-stage on python:3.12-slim: install the heavy WebRTC/media deps
# (pipecat-ai, aiortc, opencv-python, PyAV) then run the single async HTTP+WS
# server (aiohttp, ADR-0047): UI + REST + the live-voice WebSocket (/ws) + WebRTC
# signaling all on one routed port (:8090).
# Binds 0.0.0.0 for remote reachability (code default is 127.0.0.1). Non-root.
# All runtime configuration is environment-driven (VOICE_BACKEND, VOICE_BACKEND_URL,
# GRADIUM_API_KEY, VOICE_STUN, VOICE_BACKEND_STREAM, ...); no secret baked in.

FROM python:3.12-slim AS runtime

# System libraries required at runtime:
#  - libgl1 + libglib2.0-0: cv2 (opencv-python) shared-lib imports (SmallWebRTCTransport).
# aiortc/PyAV/pylibsrtp ship self-contained manylinux wheels (bundled ffmpeg/libsrtp),
# so no extra media system packages are needed.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# Resolve Python deps first so this layer is cached until requirements.txt changes.
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Non-root user.
RUN groupadd --system --gid 1001 app \
    && useradd --system --uid 1001 --gid app --home-dir /app --shell /usr/sbin/nologin app

# Application code (top-level modules are importable because server.py inserts the
# package parent — /app — onto sys.path).
COPY . /app
RUN chown -R app:app /app

USER app
EXPOSE 8090

# Health = the mic UI / static entry point served at GET / by the stdlib server.
# Uses python (always present) rather than curl/wget (absent from the slim image).
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8090/', timeout=3).status==200 else 1)" || exit 1

# --host 0.0.0.0 is required (code default binds localhost only); everything else
# is env-driven via argparse env fallbacks.
ENTRYPOINT ["python", "-m", "web_voice.server", "--host", "0.0.0.0", "--port", "8090"]
