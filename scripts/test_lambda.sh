#!/bin/bash
set -e

echo "🧪 Testing Lambda handler locally using Docker..."

# Check if sample webhook exists
if [ ! -f "samples/chatwoot_webhook.json" ]; then
    echo "❌ samples/chatwoot_webhook.json not found"
    echo "Please create a sample webhook payload first"
    exit 1
fi

echo "📋 Using webhook sample from samples/chatwoot_webhook.json"

# Run the test using our Docker image
docker run --rm \
    --env-file .env \
    -v $(pwd):/app \
    -w /app \
    posso-re-act-agent-app:latest \
    python -c "
import json
import sys
from lambda_handler import lambda_handler

# Load sample webhook payload
with open('samples/chatwoot_webhook.json', 'r') as f:
    sample_payload = json.load(f)

# Create mock Lambda event
mock_event = {
    'body': json.dumps(sample_payload)
}

print('🧪 Testing Lambda handler locally...')

try:
    result = lambda_handler(mock_event, None)
    print(f'✅ Success: {result}')
    sys.exit(0)
except Exception as e:
    print(f'❌ Error: {e}')
    import traceback
    traceback.print_exc()
    sys.exit(1)
"

echo "✅ Lambda handler test complete!"