#!/bin/bash
set -e

echo "🧪 Testing Lambda handler locally using Docker..."

# Check if sample webhook exists
if [ ! -f "samples/chatwoot_webhook.json" ]; then
    echo "❌ samples/chatwoot_webhook.json not found"
    echo "Please create a sample webhook payload first"
    exit 1
fi

echo "📋 Testing with tour booking request to trigger active task..."

# Run the test using our Docker image with a tour booking message
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

# Modify the message to request a tour booking with specific date/time
sample_payload['messages'][0]['content'] = 'I want to book a tour of the school on December 15th at 10am'
sample_payload['messages'][0]['processed_message_content'] = 'I want to book a tour of the school on December 15th at 10am'

print('🧪 Testing Lambda handler with tour booking request...')
print('📝 Message:', sample_payload['messages'][0]['content'])

# Create mock Lambda event
mock_event = {
    'body': json.dumps(sample_payload)
}

try:
    result = lambda_handler(mock_event, None)
    print(f'✅ Result: {result}')
    
    # Check if active task was created
    if 'response' in result and 'body' in result:
        response_body = json.loads(result['body'])
        print(f'📤 Response message: {response_body.get(\"message\", \"No message\")}')
    
    sys.exit(0)
except Exception as e:
    print(f'❌ Error: {e}')
    import traceback
    traceback.print_exc()
    sys.exit(1)
"

echo "✅ Lambda handler test complete!"