# syntax=docker/dockerfile:1

# ---------------------------------------------------------------------------
# Stage 1 — builder: install the package into an isolated venv.
# ---------------------------------------------------------------------------
FROM python:3.11-slim AS builder

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /src

# Create the runtime virtualenv up front so it can be copied wholesale.
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Copy only what the build backend needs first, for better layer caching.
COPY pyproject.toml README.md LICENSE ./
COPY unwind ./unwind

RUN pip install --upgrade pip build \
    && pip install .

# ---------------------------------------------------------------------------
# Stage 2 — runtime: slim image, non-root, entrypoint = unwind CLI.
# ---------------------------------------------------------------------------
FROM python:3.11-slim AS runtime

# OCI image metadata.
LABEL org.opencontainers.image.title="Unwind" \
      org.opencontainers.image.description="A reversibility layer for agentic tool use — a transparent MCP proxy that classifies which tool calls can be undone and maintains a durable cross-server undo log." \
      org.opencontainers.image.source="https://github.com/bhaskargurram-ai/unwind" \
      org.opencontainers.image.url="https://github.com/bhaskargurram-ai/unwind" \
      org.opencontainers.image.documentation="https://bhaskargurram-ai.github.io/unwind/" \
      org.opencontainers.image.licenses="Apache-2.0" \
      org.opencontainers.image.authors="Bhaskar Gurram <bhaskar@zasti.ai>" \
      org.opencontainers.image.vendor="Zasti"

ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Create an unprivileged user and a writable home for the durable undo log.
RUN useradd --create-home --uid 10001 --shell /usr/sbin/nologin unwind

# Bring over the fully built virtualenv from the builder stage.
COPY --from=builder /opt/venv /opt/venv

USER unwind
WORKDIR /home/unwind

# `unwind` is the console script; e.g.:
#   docker run ghcr.io/bhaskargurram-ai/unwind run -- <upstream cmd>
ENTRYPOINT ["unwind"]
CMD ["--help"]
