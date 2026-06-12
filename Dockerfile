FROM python:3.13-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY server/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

COPY server/ /app/server/
COPY docker/core-config.yaml /app/server/config.yaml

RUN groupadd -r agentwire \
    && useradd -r -g agentwire -m -d /home/agentwire agentwire \
    && mkdir -p /data/history /data/peers \
    && chown -R agentwire:agentwire /app /data

USER agentwire

EXPOSE 18800

ENV CORE_LISTEN_HOST=0.0.0.0 \
    CORE_LISTEN_PORT=18800 \
    AGENTWIRE_HOME=/data

VOLUME ["/data/history", "/data/peers"]

CMD ["python3", "/app/server/start.py", "--token-file", "/run/secrets/a2a-token.txt"]
