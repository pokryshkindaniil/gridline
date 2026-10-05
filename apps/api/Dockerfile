# syntax=docker/dockerfile:1
# Build context: repository root (needs packages/ and migrations/).
#   docker build -f apps/api/Dockerfile -t gridline-api .

FROM python:3.13-slim AS build
ENV PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
RUN python -m venv /opt/venv
ENV PATH=/opt/venv/bin:$PATH
WORKDIR /src
COPY packages ./packages
COPY apps/api/pyproject.toml ./apps/api/pyproject.toml
COPY apps/api/app ./apps/api/app
# Regular (non-editable) installs: the final image carries no source trees, tests or dev tooling.
RUN pip install ./packages/shared ./packages/calendar ./packages/sources ./apps/api

FROM python:3.13-slim
ENV PATH=/opt/venv/bin:$PATH PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 ENVIRONMENT=production
RUN useradd --system --uid 10001 --create-home gridline
COPY --from=build /opt/venv /opt/venv
WORKDIR /app/apps/api
COPY apps/api/alembic.ini ./alembic.ini
COPY migrations /app/migrations
COPY docker/api-entrypoint.sh /usr/local/bin/api-entrypoint.sh
USER gridline
EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=5s --start-period=40s --retries=5 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=4).status == 200 else 1)"
CMD ["api-entrypoint.sh"]
