.PHONY: infra-up infra-down infra-logs test-common install-common

## Start all local dev infrastructure (Postgres/Timescale, Redis, Kafka, OpenSearch, MinIO)
infra-up:
	docker compose -f infra/docker-compose.yml up -d
	@echo "Waiting for services to become healthy..."
	docker compose -f infra/docker-compose.yml ps

## Stop and remove local dev infrastructure
infra-down:
	docker compose -f infra/docker-compose.yml down

## Tail logs from all infra containers
infra-logs:
	docker compose -f infra/docker-compose.yml logs -f

## Install the shared platform_common library in editable mode
install-common:
	pip install -e shared/libs/platform_common

## Run the shared library's test suite
test-common:
	cd shared/libs/platform_common && python -m pytest tests/ -v
