# Shortcuts. Each line shows the plain docker command, so you can run it without make.

.PHONY: up down reset logs ps test eval smoke status lock

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
	cd backend && python -m pytest -q -m "not stack"

status:    ## which phase are we in
	@cat docs/phases/status.json

eval:      ## run the full eval suite inside the api container, against the running stack
	docker compose run --rm -e API_URL=http://api:8000 api pytest -q

smoke:     ## quick outside-in check (what a reviewer would do first)
	bash scripts/smoke.sh

lock:      ## regenerate backend/requirements.lock after editing requirements.txt
	docker run --rm -v "$(CURDIR)/backend:/w" -w /w python:3.12-slim sh -c "pip install -q -r requirements.txt && (echo '# Generated from requirements.txt with make lock'; pip freeze) > requirements.lock"
