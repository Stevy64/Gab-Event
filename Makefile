COMPOSE_DEV  := docker compose -f docker-compose.dev.yml
COMPOSE_PROD := docker compose -f docker-compose.yml

.DEFAULT_GOAL := dev

.PHONY: help dev prod up down stop restart logs migrate superuser shell clean ps health

help:
	@echo "Gab Event — commandes Docker"
	@echo "  make / make dev   Stack de développement (runserver :8000)"
	@echo "  make prod         Stack production (nginx :80 + gunicorn)"
	@echo "  make down         Arrête la stack de développement"
	@echo "  make stop         Alias de down"
	@echo "  make restart      Rebuild + relance le développement"
	@echo "  make logs         Suit les logs (dev)"
	@echo "  make migrate      Migrations Django (dev)"
	@echo "  make superuser    Crée un superutilisateur (dev)"
	@echo "  make shell        Shell Django (dev)"
	@echo "  make clean        Arrête et supprime les volumes de développement"

dev up:
	$(COMPOSE_DEV) up --build

prod:
	$(COMPOSE_PROD) up --build -d

down stop:
	-$(COMPOSE_DEV) down
	-$(COMPOSE_PROD) down

restart:
	-$(COMPOSE_DEV) down
	$(COMPOSE_DEV) up --build

logs:
	$(COMPOSE_DEV) logs -f

migrate:
	$(COMPOSE_DEV) exec gabevent-web python manage.py migrate --noinput

superuser:
	$(COMPOSE_DEV) exec gabevent-web python manage.py createsuperuser

shell:
	$(COMPOSE_DEV) exec gabevent-web python manage.py shell

ps:
	$(COMPOSE_DEV) ps

health:
	$(COMPOSE_DEV) exec gabevent-web python -c "import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:8000/health/').read().decode())"

clean:
	-$(COMPOSE_DEV) down -v
	-$(COMPOSE_PROD) down -v
