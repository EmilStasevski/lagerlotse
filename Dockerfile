# Web app and jobs (seed, report). Dependencies come from uv.lock only.
FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.12.21 /uv /bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_NO_DEV=1 PYTHONUNBUFFERED=1

WORKDIR /app
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --locked --no-install-project
COPY src ./src
RUN uv sync --locked

RUN useradd --create-home --uid 1000 lagerlotse && mkdir -p /app/reports \
    && chown lagerlotse /app/reports
USER lagerlotse
ENV PATH="/app/.venv/bin:$PATH"
EXPOSE 8000
CMD ["uvicorn", "--factory", "lagerlotse.api.app:app_factory", "--host", "0.0.0.0", "--port", "8000"]
