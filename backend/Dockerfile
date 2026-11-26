# Backend image: used by both the api and worker services.
# Build context is the repo root (so the sample files can be baked in).
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# pg_dump and psql for the backup and restore scripts, which the nightly backup service runs from this image
RUN apt-get update && apt-get install -y --no-install-recommends postgresql-client && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Dependencies first, so code changes don't reinstall everything
COPY backend/requirements.lock ./requirements.lock
RUN pip install -r requirements.lock

COPY backend/app ./app
COPY backend/evals ./evals
COPY backend/pytest.ini ./pytest.ini
COPY data/samples ./data/samples
# Docs, README, scripts and the deploy files ship in the image so every check runs inside the container too
COPY docs ./docs
COPY README.md ASSUMPTIONS.md docker-compose.yml docker-compose.prod.yml ./
COPY scripts ./scripts
COPY deploy ./deploy
COPY .github ./.github

RUN useradd --create-home --uid 10001 app && mkdir -p /tmp/bidbench && chown -R app /app /tmp/bidbench
USER app

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
