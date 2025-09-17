#!/bin/bash
set -e

echo "🚀 Setting up AWS Parameter Store from .env file..."

# No need to build our heavy app image - use lightweight Python image

# Extract AWS credentials from aws configure
echo "📋 Extracting AWS credentials..."

AWS_PROFILE=posso
AWS_ACCESS_KEY_ID=$(aws configure get aws_access_key_id 2>/dev/null || echo "")
AWS_SECRET_ACCESS_KEY=$(aws configure get aws_secret_access_key 2>/dev/null || echo "")
AWS_DEFAULT_REGION=$(aws configure get region 2>/dev/null || echo "ap-southeast-1")
AWS_SESSION_TOKEN=$(aws configure get aws_session_token 2>/dev/null || echo "")

# Check if credentials were found
if [ -z "$AWS_ACCESS_KEY_ID" ] || [ -z "$AWS_SECRET_ACCESS_KEY" ]; then
    echo "❌ AWS credentials not found."
    echo "Please run: aws configure"
    echo "Or set AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY environment variables"
    exit 1
fi

echo "✅ AWS credentials found for region: ${AWS_DEFAULT_REGION}"

# Run the parameter setup script in lightweight Python container
echo "Running AWS parameter setup in Python container..."
docker run --rm \
    --env-file .env \
    -e AWS_ACCESS_KEY_ID="${AWS_ACCESS_KEY_ID}" \
    -e AWS_SECRET_ACCESS_KEY="${AWS_SECRET_ACCESS_KEY}" \
    -e AWS_SESSION_TOKEN="${AWS_SESSION_TOKEN}" \
    -e AWS_DEFAULT_REGION="${AWS_DEFAULT_REGION}" \
    -v $(pwd):/app \
    -w /app \
    python:3.11-slim \
    bash -c "pip install boto3 python-dotenv loguru && python scripts/setup_aws_params.py --upload --region ${AWS_DEFAULT_REGION}"

echo "✅ AWS Parameter Store setup complete!"
echo "🚀 Ready to deploy with: serverless deploy --region ${AWS_DEFAULT_REGION}"