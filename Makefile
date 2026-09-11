.PHONY: infra-up infra-down foundation-test demo

infra-up:
	docker compose -f infra/docker-compose.yml up -d

infra-down:
	docker compose -f infra/docker-compose.yml down

foundation-test:
	python -m pytest shared/libs/platform_common/tests -q

demo:
	python app.py
