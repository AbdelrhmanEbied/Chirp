FROM chirp-base:latest AS builder

WORKDIR /srv

COPY services/auth/pyproject.toml /srv/service/pyproject.toml
COPY services/auth/app /srv/service/app
COPY services/auth/migrations /srv/service/migrations
COPY services/auth/alembic.ini /srv/service/alembic.ini

RUN pip install --no-cache-dir argon2-cffi email-validator

EXPOSE 8001
HEALTHCHECK --interval=10s --timeout=3s --start-period=15s --retries=5 \
  CMD curl -fsS http://localhost:8001/health/live || exit 1
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8001 --workers 2 --proxy-headers --forwarded-allow-ips '*' --timeout-graceful-shutdown 30 --limit-max-requests 10000"]
