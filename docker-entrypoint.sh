#!/bin/bash
set -e

# Wait for Redis to be ready
echo "Waiting for Redis..."
until redis-cli -h "${REDIS_HOST:-redis}" -p "${REDIS_PORT:-6379}" ping > /dev/null 2>&1; do
  echo "Redis is unavailable - sleeping"
  sleep 1
done

echo "Redis is ready!"

# Execute the command passed to the container
exec "$@"

