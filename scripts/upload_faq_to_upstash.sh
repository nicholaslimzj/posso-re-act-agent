#!/bin/bash
set -e

# Check if clear mode is requested
if [ "$1" = "clear" ]; then
    echo "🗑️ Clearing Upstash Vector database..."
    MODE_ARGS="clear"
else
    echo "🚀 Uploading FAQ data to Upstash Vector..."
    MODE_ARGS=""
fi

# Use a lightweight Python image and install only what we need
echo "Running script in Docker container..."
docker run --rm \
    --env-file .env \
    -v $(pwd)/data:/app/data \
    -v $(pwd)/scripts:/app/scripts \
    -w /app \
    python:3.11-slim \
    bash -c "
        echo 'Installing requirements...' && \
        pip install --no-cache-dir httpx python-dotenv loguru && \
        echo 'Running script...' && \
        python scripts/upload_faq_to_upstash.py $MODE_ARGS
    "

if [ "$1" = "clear" ]; then
    echo "✅ Database cleared!"
else
    echo "✅ Upload complete!"
fi