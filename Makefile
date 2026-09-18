SHELL := /bin/bash
COMPOSE := docker compose

.PHONY: help up down logs ps reset mock shell-console shell-dc
help:
	@echo "Directory Control Center"
	@echo "  make up             build and start the Samba AD DC + console"
	@echo "  make down           stop and remove containers"
	@echo "  make logs           tail logs"
	@echo "  make ps             status"
	@echo "  make reset          destroy volumes (wipes the domain) and restart"
	@echo "  make mock           run the console alone against built-in sample data"
	@echo "  make shell-console  open a shell in the console container"
	@echo "  make shell-dc       open a shell in the DC container"

up:
	$(COMPOSE) up -d --build

down:
	$(COMPOSE) down

logs:
	$(COMPOSE) logs -f --tail=100

ps:
	$(COMPOSE) ps

reset:
	$(COMPOSE) down -v
	$(COMPOSE) up -d --build

mock:
	DCC_MOCK=1 $(COMPOSE) up -d --build console
	@echo "Console (mock mode): http://localhost:$${CONSOLE_PORT:-8000}"

shell-console:
	$(COMPOSE) exec console bash

shell-dc:
	$(COMPOSE) exec dc bash
