.PHONY: up down build test backend-test frontend-test installer-test migrate logs

COMPOSE_DEV := docker compose -f docker-compose.yml -f compose.dev.yaml

up:
	$(COMPOSE_DEV) up -d

down:
	docker compose down

build:
	$(COMPOSE_DEV) build

logs:
	$(COMPOSE_DEV) logs -f api worker web

migrate:
	cd backend && .venv/bin/alembic upgrade head

backend-test:
	cd backend && .venv/bin/pytest -q

frontend-test:
	cd frontend && npm test && npm run build

installer-test:
	bash installer/tests/run.sh
	bash installer/pack.sh /tmp/install-lesspaper-ngl.sh
	bash -n /tmp/install-lesspaper-ngl.sh
	test -x /tmp/install-folium.sh
	cmp -s /tmp/install-lesspaper-ngl.sh /tmp/install-folium.sh

test: backend-test frontend-test installer-test
