#!/bin/bash
# Development runner script with auto-reload

echo "🚀 Starting Posso ReAct Agent in DEVELOPMENT mode with auto-reload..."

# Export development environment variables
export RUN_MODE=web
export DEV_MODE=true

# Option 1: Run with docker-compose (recommended)
echo "Using Docker Compose for development..."
docker-compose -f docker-compose.dev.yml up --build

# Option 2: Run locally (uncomment if not using Docker)
# echo "Running locally..."
# python main.py