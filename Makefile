# Shortcuts. Each line shows the plain docker command, so you can run it without make.

# Use the local virtualenv when it exists, otherwise whatever `python` is on PATH.
PY := $(shell [ -x "$(CURDIR)/.venv/bin/python" ] && echo "$(CURDIR)/.venv/bin/python" || echo python)

.PHONY: up down reset logs ps test lint eval smoke status lock venv env env-lock

up:        ## build and start everything in the background
	docker compose up --build -d
	@echo "UI:  http://localhost:3000   API docs: http://localhost:8000/docs"

down:      ## stop everything (keeps the database)
	docker compose down

reset:     ## stop everything AND wipe the database, then start fresh
	docker compose down -v
	docker compose up --build -d

logs:      ## follow logs from all services
	docker compose logs -f --tail=100

ps:        ## show which services are running and healthy
	docker compose ps

test:      ## fast evals on your machine, no Docker (needs Python 3.12 + backend/requirements.lock)
	cd backend && $(PY) -m pytest -q -m "not stack"

lint:      ## PEP 8 check and format check on the backend (same two commands CI runs)
	cd backend && $(PY) -m ruff check .
	cd backend && $(PY) -m ruff format --check .

status:    ## which phase are we in
	@cat docs/phases/status.json

eval:      ## run the full eval suite inside the api container, against the running stack
	docker compose run --rm -e API_URL=http://api:8000 api pytest -q

smoke:     ## quick outside-in check (what a reviewer would do first)
	bash scripts/smoke.sh

venv:      ## create .venv with Python 3.12 and install backend/requirements.lock
	python3.12 -m venv .venv
	.venv/bin/python -m pip install -q --upgrade pip
	.venv/bin/python -m pip install -q -r backend/requirements.lock
	@echo "venv ready: $(CURDIR)/.venv/bin/python"

lock:      ## regenerate backend/requirements.lock after editing requirements.txt
	docker run --rm -v "$(CURDIR)/backend:/w" -w /w python:3.12-slim sh -c "pip install -q -r requirements.txt && (echo '# Generated from requirements.txt with make lock'; pip freeze) > requirements.lock"

env:       ## unlock the demo .env from deploy/env.enc (PHRASE comes with the submission note)
	@test -n "$(PHRASE)" || { echo "usage: make env PHRASE=<phrase from the submission note>"; exit 1; }
	@openssl enc -d -aes-256-cbc -pbkdf2 -in deploy/env.enc -out .env -pass pass:"$(PHRASE)" && echo ".env unlocked; now: docker compose up -d"

env-lock:  ## encrypt your local .env into deploy/env.enc so the repo carries the key without exposing it
	@test -n "$(PHRASE)" || { echo "usage: make env-lock PHRASE=<a phrase you will send with the submission>"; exit 1; }
	@openssl enc -aes-256-cbc -pbkdf2 -salt -in .env -out deploy/env.enc -pass pass:"$(PHRASE)" && echo "deploy/env.enc written; commit it, keep the phrase out of the repo"
