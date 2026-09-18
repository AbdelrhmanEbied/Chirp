FROM chirp-base:latest AS builder

WORKDIR /srv

COPY services/graph/pyproject.toml /srv/service/pyproject.toml
COPY services/graph/app /srv/service/app
COPY services/graph/migrations /srv/service/migrations
COPY services/graph/alembic.ini /srv/service/alembic.ini

EXPOSE 8004
HEALTHCHECK --interval=10s --timeout=3s --start-period=15s --retries=5 \
  CMD curl -fsS http://localhost:8004/health/live || exit 1
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8004 --workers 2 --proxy-headers --forwarded-allow-ips '*' --timeout-graceful-shutdown 30 --limit-max-requests 10000"]
