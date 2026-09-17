# syntax=docker/dockerfile:1
FROM python:3.12-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /srv

# Build tools are needed for argon2-cffi wheels on some platforms; they are
# dropped from the final image.
RUN apt-get update \
 && apt-get install -y --no-install-recommends build-essential curl \
 && rm -rf /var/lib/apt/lists/*

# The shared library is copied first: it changes less often than service code,
# so this layer stays cached across most rebuilds.
COPY libs/chirp-common /srv/libs/chirp-common
RUN pip install --no-cache-dir /srv/libs/chirp-common

COPY services/user/pyproject.toml /srv/service/pyproject.toml
COPY services/user/app /srv/service/app
COPY services/user/migrations /srv/service/migrations
COPY services/user/alembic.ini /srv/service/alembic.ini

WORKDIR /srv/service
RUN pip install --no-cache-dir --no-deps . \
 && pip install --no-cache-dir "uvicorn[standard]>=0.30" \
      "psycopg[binary]>=3.2" \
 && apt-get purge -y build-essential && apt-get autoremove -y

RUN useradd --create-home --uid 10001 chirp && chown -R chirp /srv
USER chirp

EXPOSE 8002
HEALTHCHECK --interval=10s --timeout=3s --start-period=15s --retries=5 \
  CMD curl -fsS http://localhost:8002/health/live || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8002"]
