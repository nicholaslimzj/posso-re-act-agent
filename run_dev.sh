#!/bin/bash
# Development runner script with configurable options

# Default values
WORKERS=1
DEV_MODE=true
AUTO_RELOAD=true

# Parse command line arguments
while [[ $# -gt 0 ]]; do
  case $1 in
    -w|--workers)
      WORKERS="$2"
      shift # past argument
      shift # past value
      ;;
    --prod-mode)
      DEV_MODE=false
      AUTO_RELOAD=false
      if [[ $WORKERS -eq 1 ]]; then
        WORKERS=4  # Default to 4 workers in prod-like mode
      fi
      shift # past argument
      ;;
    --no-reload)
      AUTO_RELOAD=false
      shift # past argument
      ;;
    -h|--help)
      echo "Usage: $0 [OPTIONS]"
      echo "Options:"
      echo "  -w, --workers NUM     Number of worker processes (default: 1 for dev, 4 for prod-mode)"
      echo "  --prod-mode           Run in production-like mode (no auto-reload, multiple workers)"
      echo "  --no-reload           Disable auto-reload but keep dev settings"
      echo "  -h, --help            Show this help message"
      echo ""
      echo "Examples:"
      echo "  $0                    # Default dev mode with auto-reload"
      echo "  $0 -w 4               # Dev mode with 4 workers (no auto-reload)"
      echo "  $0 --prod-mode        # Production-like mode with 4 workers"
      echo "  $0 --prod-mode -w 8   # Production-like mode with 8 workers"
      exit 0
      ;;
    -*|--*)
      echo "Unknown option $1"
      echo "Use -h or --help for usage information"
      exit 1
      ;;
  esac
done

# If workers > 1, disable auto-reload (uvicorn limitation)
if [[ $WORKERS -gt 1 ]]; then
  AUTO_RELOAD=false
fi

# Set DEV_MODE based on auto-reload setting (for consistency)
if [[ $AUTO_RELOAD == false ]]; then
  DEV_MODE=false
fi

# Display configuration
echo "🚀 Starting Posso ReAct Agent with configuration:"
echo "   Workers: $WORKERS"
echo "   Dev Mode: $DEV_MODE"
echo "   Auto-reload: $AUTO_RELOAD"

# Export environment variables
export RUN_MODE=web
export DEV_MODE=$DEV_MODE
export WORKERS=$WORKERS

# Run with docker-compose
echo "Using Docker Compose..."
docker-compose -f docker-compose.dev.yml up