# syntax=docker/dockerfile:1
FROM python:3.12-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /srv

RUN apt-get update \
 && apt-get install -y --no-install-recommends build-essential curl \
 && rm -rf /var/lib/apt/lists/*

COPY libs/chirp-common /srv/libs/chirp-common
RUN pip install --no-cache-dir /srv/libs/chirp-common

COPY services/gateway/pyproject.toml /srv/service/pyproject.toml
COPY services/gateway/app /srv/service/app

WORKDIR /srv/service
RUN pip install --no-cache-dir --no-deps . \
 && pip install --no-cache-dir "uvicorn[standard]>=0.30" "httpx>=0.27" "redis>=5.0" \
 && apt-get purge -y build-essential && apt-get autoremove -y

RUN useradd --create-home --uid 10001 chirp && chown -R chirp /srv
USER chirp

EXPOSE 8000
HEALTHCHECK --interval=10s --timeout=3s --start-period=15s --retries=5 \
  CMD curl -fsS http://localhost:8000/health/live || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
