#!/bin/bash
# Docker helper script for Real-time AI Recommender

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Function to print colored messages
print_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

print_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check if .env file exists
check_env() {
    if [ ! -f .env ]; then
        print_warn ".env file not found. Creating from .env.example..."
        if [ -f .env.example ]; then
            cp .env.example .env
            print_info ".env file created. Please edit it if needed."
        else
            print_error ".env.example not found. Please create .env manually."
            exit 1
        fi
    fi
}

# Function to start services
start() {
    local mode=${1:-prod}
    check_env
    
    if [ "$mode" == "dev" ]; then
        print_info "Starting services in DEVELOPMENT mode..."
        docker-compose -f docker-compose.dev.yml up -d
    else
        print_info "Starting services in PRODUCTION mode..."
        docker-compose up -d
    fi
    
    print_info "Waiting for services to be ready..."
    sleep 5
    
    print_info "Services started! Access API at http://localhost:8000"
    print_info "API Docs: http://localhost:8000/docs"
    print_info "Health Check: http://localhost:8000/health"
}

# Function to stop services
stop() {
    local mode=${1:-prod}
    
    if [ "$mode" == "dev" ]; then
        print_info "Stopping development services..."
        docker-compose -f docker-compose.dev.yml down
    else
        print_info "Stopping production services..."
        docker-compose down
    fi
}

# Function to view logs
logs() {
    local service=${1:-""}
    local mode=${2:-prod}
    local follow=${3:-"-f"}
    
    if [ "$mode" == "dev" ]; then
        if [ -z "$service" ]; then
            docker-compose -f docker-compose.dev.yml logs $follow
        else
            docker-compose -f docker-compose.dev.yml logs $follow "$service"
        fi
    else
        if [ -z "$service" ]; then
            docker-compose logs $follow
        else
            docker-compose logs $follow "$service"
        fi
    fi
}

# Function to restart services
restart() {
    local service=${1:-""}
    local mode=${2:-prod}
    
    if [ "$mode" == "dev" ]; then
        if [ -z "$service" ]; then
            docker-compose -f docker-compose.dev.yml restart
        else
            docker-compose -f docker-compose.dev.yml restart "$service"
        fi
    else
        if [ -z "$service" ]; then
            docker-compose restart
        else
            docker-compose restart "$service"
        fi
    fi
}

# Function to show status
status() {
    local mode=${1:-prod}
    
    if [ "$mode" == "dev" ]; then
        docker-compose -f docker-compose.dev.yml ps
    else
        docker-compose ps
    fi
}

# Function to build images
build() {
    local mode=${1:-prod}
    local nocache=${2:-""}
    
    if [ "$mode" == "dev" ]; then
        if [ "$nocache" == "--no-cache" ]; then
            docker-compose -f docker-compose.dev.yml build --no-cache
        else
            docker-compose -f docker-compose.dev.yml build
        fi
    else
        if [ "$nocache" == "--no-cache" ]; then
            docker-compose build --no-cache
        else
            docker-compose build
        fi
    fi
}

# Function to clean up
clean() {
    print_warn "This will remove all containers, networks, and volumes!"
    read -p "Are you sure? (y/N) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        print_info "Stopping and removing containers..."
        docker-compose down -v
        docker-compose -f docker-compose.dev.yml down -v
        
        print_info "Removing unused images..."
        docker image prune -f
        
        print_info "Cleanup complete!"
    else
        print_info "Cleanup cancelled."
    fi
}

# Function to execute command in container
exec_cmd() {
    local service=${1:-api}
    local command=${2:-bash}
    local mode=${3:-prod}
    
    if [ "$mode" == "dev" ]; then
        docker-compose -f docker-compose.dev.yml exec "$service" "$command"
    else
        docker-compose exec "$service" "$command"
    fi
}

# Function to show help
show_help() {
    echo "Docker Helper Script for Real-time AI Recommender"
    echo ""
    echo "Usage: $0 [command] [options]"
    echo ""
    echo "Commands:"
    echo "  start [dev|prod]      Start services (default: prod)"
    echo "  stop [dev|prod]        Stop services (default: prod)"
    echo "  restart [service]      Restart services or specific service"
    echo "  logs [service]         View logs (add service name for specific service)"
    echo "  status                 Show service status"
    echo "  build [--no-cache]     Build Docker images"
    echo "  exec [service] [cmd]   Execute command in container (default: bash)"
    echo "  clean                  Remove all containers, volumes, and networks"
    echo "  help                   Show this help message"
    echo ""
    echo "Examples:"
    echo "  $0 start dev           # Start in development mode"
    echo "  $0 logs api            # View API logs"
    echo "  $0 restart redis      # Restart Redis service"
    echo "  $0 exec api bash       # Open bash in API container"
    echo "  $0 clean               # Clean up everything"
    echo ""
}

# Main command handler
case "${1:-help}" in
    start)
        start "${2:-prod}"
        ;;
    stop)
        stop "${2:-prod}"
        ;;
    restart)
        restart "${2:-}" "${3:-prod}"
        ;;
    logs)
        logs "${2:-}" "${3:-prod}" "-f"
        ;;
    status)
        status "${2:-prod}"
        ;;
    build)
        build "${2:-prod}" "${3:-}"
        ;;
    exec)
        exec_cmd "${2:-api}" "${3:-bash}" "${4:-prod}"
        ;;
    clean)
        clean
        ;;
    help|--help|-h)
        show_help
        ;;
    *)
        print_error "Unknown command: $1"
        show_help
        exit 1
        ;;
esac

