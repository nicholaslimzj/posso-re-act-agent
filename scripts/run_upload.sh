#!/bin/bash
set -e

echo "🚀 Uploading FAQ embeddings to Upstash Vector..."

# Build the Docker image if it doesn't exist
if ! docker images | grep -q "posso-re-act-agent-app"; then
    echo "Building Docker image..."
    docker build -t posso-re-act-agent-app .
fi

# Run the upload script inside the container
echo "Running upload script in Docker container..."
docker run --rm \
    --env-file .env \
    -v $(pwd)/data:/app/data \
    -v $(pwd)/scripts:/app/scripts \
    posso-re-act-agent-app \
    python scripts/upload_faq_to_upstash.py

echo "✅ Upload complete!"