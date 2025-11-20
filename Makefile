.PHONY: help start stop restart logs status build clean exec test dev

# Default target
help:
	@echo "Docker Commands for Real-time AI Recommender"
	@echo ""
	@echo "Usage: make [target]"
	@echo ""
	@echo "Targets:"
	@echo "  make start          - Start services (production)"
	@echo "  make dev            - Start services (development with hot-reload)"
	@echo "  make stop           - Stop services"
	@echo "  make restart        - Restart services"
	@echo "  make logs           - View logs (all services)"
	@echo "  make logs-api       - View API logs"
	@echo "  make logs-redis     - View Redis logs"
	@echo "  make logs-consumer  - View consumer logs"
	@echo "  make status         - Show service status"
	@echo "  make build          - Build Docker images"
	@echo "  make clean          - Remove all containers and volumes"
	@echo "  make exec-api       - Execute bash in API container"
	@echo "  make exec-consumer  - Execute bash in consumer container"
	@echo "  make test           - Run tests in container"
	@echo "  make health         - Check service health"
	@echo ""

# Start services (production)
start:
	@echo "Starting services in PRODUCTION mode..."
	@docker-compose up -d
	@echo "Services started! Access API at http://localhost:8000"
	@echo "API Docs: http://localhost:8000/docs"

# Start services (development)
dev:
	@echo "Starting services in DEVELOPMENT mode..."
	@docker-compose -f docker-compose.dev.yml up -d
	@echo "Services started! Access API at http://localhost:8000"
	@echo "API Docs: http://localhost:8000/docs"

# Stop services
stop:
	@echo "Stopping services..."
	@docker-compose down
	@docker-compose -f docker-compose.dev.yml down

# Restart services
restart:
	@echo "Restarting services..."
	@docker-compose restart

# View logs
logs:
	@docker-compose logs -f

logs-api:
	@docker-compose logs -f api

logs-redis:
	@docker-compose logs -f redis

logs-consumer:
	@docker-compose logs -f stream-consumer

# Show status
status:
	@docker-compose ps

# Build images
build:
	@echo "Building Docker images..."
	@docker-compose build

# Clean up
clean:
	@echo "This will remove all containers, networks, and volumes!"
	@read -p "Are you sure? [y/N] " -n 1 -r; \
	echo; \
	if [[ $$REPLY =~ ^[Yy]$$ ]]; then \
		docker-compose down -v; \
		docker-compose -f docker-compose.dev.yml down -v; \
		docker image prune -f; \
		echo "Cleanup complete!"; \
	fi

# Execute commands in containers
exec-api:
	@docker-compose exec api bash

exec-consumer:
	@docker-compose exec stream-consumer bash

exec-redis:
	@docker-compose exec redis redis-cli

# Run tests
test:
	@docker-compose exec api pytest

# Health check
health:
	@echo "Checking service health..."
	@echo "API: $$(curl -s http://localhost:8000/health || echo 'NOT AVAILABLE')"
	@echo "Redis: $$(docker-compose exec -T redis redis-cli ping || echo 'NOT AVAILABLE')"

# Rebuild without cache
rebuild:
	@echo "Rebuilding images without cache..."
	@docker-compose build --no-cache

# Start with logs
up:
	@docker-compose up

# Start development with logs
up-dev:
	@docker-compose -f docker-compose.dev.yml up

