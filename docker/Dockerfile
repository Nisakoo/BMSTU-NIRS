FROM python:3.12-slim AS build
WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy
ARG SPEECH_ENABLED=false
ARG RAG_HYBRID_ENABLED=false
COPY --from=ghcr.io/astral-sh/uv:0.12.13 /uv /bin/uv
COPY docker/backend-features.sh /backend-features.sh
COPY backend/pyproject.toml backend/uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    . /backend-features.sh && sync_backend --no-install-project

COPY backend/README.md ./
COPY backend/src ./src
RUN --mount=type=cache,target=/root/.cache/uv \
    . /backend-features.sh && sync_backend

FROM python:3.12-slim AS runtime
WORKDIR /app
ARG TARGETARCH
ARG SPEECH_ENABLED=false
ARG RAG_HYBRID_ENABLED=false
RUN --mount=type=bind,source=docker/backend-features.sh,target=/backend-features.sh \
    --mount=type=cache,id=smeshariki-apt-cache-${TARGETARCH},target=/var/cache/apt,sharing=locked \
    --mount=type=cache,id=smeshariki-apt-lists-${TARGETARCH},target=/var/lib/apt/lists,sharing=locked \
    set -eu; \
    . /backend-features.sh; \
    set --; \
    if feature_enabled "$SPEECH_ENABLED"; then \
        set -- ffmpeg libgomp1; \
    elif feature_enabled "$RAG_HYBRID_ENABLED"; then \
        set -- libgomp1; \
    fi; \
    if [ "$#" -gt 0 ]; then \
        if [ -f /etc/apt/apt.conf.d/docker-clean ]; then \
            mv /etc/apt/apt.conf.d/docker-clean /tmp/docker-clean; \
        fi; \
        apt-get update; \
        apt-get install -y --no-install-recommends "$@"; \
        if [ -f /tmp/docker-clean ]; then \
            mv /tmp/docker-clean /etc/apt/apt.conf.d/docker-clean; \
        fi; \
    fi

ENV VIRTUAL_ENV=/app/.venv \
    PATH="/app/.venv/bin:$PATH"
COPY --link --from=build /app/.venv /app/.venv

EXPOSE 8000

CMD ["uvicorn", "smeshariki_ai.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]
