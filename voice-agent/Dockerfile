FROM python:3.12-slim

WORKDIR /app

RUN pip install --no-cache-dir uv

COPY pyproject.toml .
RUN uv pip install --system -e ".[dev]" 2>/dev/null || uv pip install --system -e .

COPY agent/ agent/

CMD ["python", "-m", "agent.bridge_server"]
