# syntax=docker/dockerfile:1
FROM python:3.12-slim AS builder

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /srv

COPY libs/chirp-common /srv/libs/chirp-common
RUN pip install --no-cache-dir /srv/libs/chirp-common

COPY services/timeline/pyproject.toml /srv/service/pyproject.toml
COPY services/timeline/app /srv/service/app
COPY services/timeline/migrations /srv/service/migrations
COPY services/timeline/alembic.ini /srv/service/alembic.ini

WORKDIR /srv/service
RUN pip install --no-cache-dir --no-deps . \
 && pip install --no-cache-dir "uvicorn[standard]>=0.30" "psycopg[binary]>=3.2"

FROM python:3.12-slim AS runtime

RUN apt-get update \
 && apt-get install -y --no-install-recommends curl \
 && rm -rf /var/lib/apt/lists/*

COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin
COPY --from=builder /srv/service /srv/service

RUN useradd --create-home --uid 10001 chirp && chown -R chirp /srv
USER chirp

WORKDIR /srv/service

EXPOSE 8005
HEALTHCHECK --interval=10s --timeout=3s --start-period=15s --retries=5 \
  CMD curl -fsS http://localhost:8005/health/live || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8005", \
     "--workers", "2", "--proxy-headers", "--forwarded-allow-ips", "*", \
     "--timeout-graceful-shutdown", "30", "--limit-max-requests", "10000"]
