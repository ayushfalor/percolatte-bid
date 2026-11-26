# Runbook

Plain-language guide to running, checking and fixing the app.

## What runs where

`docker compose up` starts four containers:

| Container | What it is | Port on your machine |
|---|---|---|
| db | Postgres 16, data kept in a Docker volume called `pgdata` | none (on purpose, avoids clashes) |
| api | FastAPI backend; creates tables and loads sample files on start | 8000 |
| worker | Runs agent jobs from the queue | none |
| web | nginx serving the React UI and forwarding `/api` to the api | 3000 |

Start order is automatic: db healthy, then api healthy, then worker and web.

## Everyday commands

| Want to | With make | Without make |
|---|---|---|
| Start (background) | `make up` | `docker compose up --build -d` |
| See what is running | `make ps` | `docker compose ps` |
| Follow logs | `make logs` | `docker compose logs -f --tail=100` |
| Stop | `make down` | `docker compose down` |
| Stop and wipe the database | `make reset` | `docker compose down -v && docker compose up --build -d` |
| Run all evals | `make eval` | `docker compose run --rm -e API_URL=http://api:8000 api pytest -q` |
| Smoke test | `make smoke` | `bash scripts/smoke.sh` |

On Windows, run these in a WSL terminal (Ubuntu) or Git Bash.

## First-time setup

- **Mac:** install Docker Desktop, open it once, wait for "Engine running".
- **Windows:** install Docker Desktop with the WSL 2 option, then clone the repo inside WSL
  (for example `~/code`), not under `C:\`, for much faster builds.
- **Linux:** install Docker Engine and the compose plugin; add yourself to the `docker` group.

## Before submitting: the fresh-clone test

CI does this on every push, but do it once yourself too:

1. `git clone` the repo into a new folder (no `.env`, nothing cached).
2. Follow the README exactly: `docker compose up --build`.
3. Open http://localhost:3000, all four lights green.
4. `make eval` passes. `make smoke` passes.
5. Upload a workbook the app has never seen; it is read and goal seek works.

## Troubleshooting

| Symptom | Fix |
|---|---|
| `port is already allocated` | Something else uses 3000 or 8000. `cp .env.example .env`, set `WEB_PORT=3100` and `API_PORT=8100`, start again |
| `Cannot connect to the Docker daemon` | Docker Desktop is not running. Start it and wait for "Engine running" |
| UI says it can't reach the API | `docker compose ps` (is api healthy?), then `docker compose logs api` |
| Runs stay `queued` | The worker is down: `docker compose logs worker`, then `docker compose up -d worker` |
| Errors about missing columns after changing `models.py` | Tables are created on start, not migrated. `make reset` |
| Build very slow on Windows | Move the repo inside WSL (see setup) |
| `bash: scripts/smoke.sh: /usr/bin/env: bash\r` | Windows line endings. `git config core.autocrlf input`, then clone again (`.gitattributes` prevents this for new clones) |
| Out of disk | `docker system prune` (removes stopped containers and old images) |

## Deploying to a VM

One small VM (2 vCPU, 4 GB) with Docker Engine and the compose plugin is enough.

1. On the VM: `sudo mkdir -p /opt/bid-workbench && sudo chown $USER /opt/bid-workbench`, then
   `git clone https://github.com/ayushfalor/percolatte-bid.git /opt/bid-workbench`.
2. `cd /opt/bid-workbench && cp .env.example .env`. Set `POSTGRES_PASSWORD` to something real.
   Set `DOMAIN=bid.example.com` if a domain points at the VM (Caddy then does HTTPS); leave it
   empty for plain HTTP. Set `ANTHROPIC_API_KEY` only if you want live extraction.
3. `docker compose -f docker-compose.yml -f docker-compose.prod.yml up --build -d`.
4. `bash scripts/smoke.sh` with `API_URL` and `WEB_URL` set to the public address.

After that, deploys come from GitHub. Add four repository secrets: `DEPLOY_HOST`, `DEPLOY_USER`,
`DEPLOY_SSH_KEY` (a private key whose public half is in the VM user's `authorized_keys`) and
`DEPLOY_URL`. Then `git tag v1.0.0 && git push origin v1.0.0` runs `.github/workflows/deploy.yml`:
it checks out the tag on the VM, restarts the stack, waits for health, runs the smoke test and
the deployed-app check. Nothing secret is in the repo; `.env` is ignored.

## Backups and restore

The `backup` service in the production file runs `scripts/backup-db.sh /backups` every 24 hours
and keeps 14 days of `bidbench-<timestamp>.sql.gz` in the `backups` volume. To copy a dump out:
`docker compose cp backup:/backups ./backups`. To take one by hand from the host:
`bash scripts/backup-db.sh ./backups`.

Restore checks a dump without touching the live data: `bash scripts/restore-db.sh backups/<file>`
loads it into a scratch database, prints `documents: N, runs: M`, and drops the scratch database.
To replace the live database: stop the api and worker (`docker compose stop api worker`), run
`FORCE=1 bash scripts/restore-db.sh backups/<file> bidbench`, then `docker compose start api worker`.

## Changing Python dependencies

Edit `backend/requirements.txt`, run `make lock` to regenerate `backend/requirements.lock`
(the exact versions Docker installs), commit both.
