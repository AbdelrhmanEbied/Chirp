FROM chirp-base:latest AS builder

WORKDIR /srv

COPY services/post/pyproject.toml /srv/service/pyproject.toml
COPY services/post/app /srv/service/app
COPY services/post/migrations /srv/service/migrations
COPY services/post/alembic.ini /srv/service/alembic.ini

EXPOSE 8003
HEALTHCHECK --interval=10s --timeout=3s --start-period=15s --retries=5 \
  CMD curl -fsS http://localhost:8003/health/live || exit 1
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8003 --workers 2 --proxy-headers --forwarded-allow-ips '*' --timeout-graceful-shutdown 30 --limit-max-requests 10000"]
