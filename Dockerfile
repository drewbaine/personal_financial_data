FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.11 /uv /usr/local/bin/uv

WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_NO_DEV=1

COPY pyproject.toml uv.lock .python-version ./
RUN uv sync --locked --no-install-project

COPY src ./src
RUN uv sync --locked

RUN useradd --create-home finance && mkdir -p /app/data && chown finance /app/data
USER finance
ENV PATH="/app/.venv/bin:$PATH"

ENTRYPOINT ["finance"]
CMD ["--help"]
