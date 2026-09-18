FROM chirp-base:latest AS builder

WORKDIR /srv

COPY services/media/pyproject.toml /srv/service/pyproject.toml
COPY services/media/app /srv/service/app
COPY services/media/migrations /srv/service/migrations
COPY services/media/alembic.ini /srv/service/alembic.ini

RUN pip install --no-cache-dir python-multipart boto3

EXPOSE 8009
HEALTHCHECK --interval=10s --timeout=3s --start-period=15s --retries=5 \
  CMD curl -fsS http://localhost:8009/health/live || exit 1
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8009 --workers 2 --proxy-headers --forwarded-allow-ips '*' --timeout-graceful-shutdown 30 --limit-max-requests 10000"]
