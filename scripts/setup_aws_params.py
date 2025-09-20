#!/usr/bin/env python3
"""
Upload .env variables to AWS Systems Manager Parameter Store
"""

import boto3
import os
from dotenv import load_dotenv
from loguru import logger

# Load environment variables
load_dotenv()

def upload_env_to_parameter_store(region='ap-southeast-1'):
    """Upload .env variables to AWS Parameter Store"""
    
    # Initialize AWS SSM client
    ssm = boto3.client('ssm', region_name=region)
    
    # Mapping of .env variables to Parameter Store paths
    env_to_param_mapping = {
        'UPSTASH_VECTOR_REST_URL': '/posso/upstash-vector-url',
        'UPSTASH_VECTOR_REST_TOKEN': '/posso/upstash-vector-token', 
        'REDIS_URL': '/posso/redis-url',
        'OPENROUTER_API_KEY': '/posso/openrouter-key',
        'MODEL_NAME': '/posso/model-name',
        'RESPONSE_CRAFTING_MODEL': '/posso/response-crafting-model',
        'CHATWOOT_API_URL': '/posso/chatwoot-api-url',
        'CHATWOOT_API_KEY': '/posso/chatwoot-key',
        'CHATWOOT_ACCOUNT_ID': '/posso/chatwoot-account-id',
        'PIPEDRIVE_API_URL': '/posso/pipedrive-api-url',
        'PIPEDRIVE_APIV2_URL': '/posso/pipedrive-apiv2-url',
        'PIPEDRIVE_API_KEYS_JSON': '/posso/pipedrive-api-keys',
        'LANGCHAIN_TRACING_V2': '/posso/langchain-tracing',
        'LANGCHAIN_API_KEY': '/posso/langchain-key'
    }
    
    logger.info(f"🚀 Uploading environment variables to Parameter Store in {region}")
    
    success_count = 0
    skip_count = 0
    
    for env_var, param_path in env_to_param_mapping.items():
        value = os.getenv(env_var)
        
        if not value:
            logger.warning(f"⚠️  Skipping {env_var} - not found in .env")
            skip_count += 1
            continue
            
        try:
            # Check if parameter already exists
            try:
                existing = ssm.get_parameter(Name=param_path, WithDecryption=True)
                if existing['Parameter']['Value'] == value:
                    logger.info(f"✅ {param_path} - unchanged")
                    success_count += 1
                    continue
                else:
                    logger.info(f"🔄 {param_path} - updating...")
            except ssm.exceptions.ParameterNotFound:
                logger.info(f"➕ {param_path} - creating...")
            
            # Put parameter (create or update)
            ssm.put_parameter(
                Name=param_path,
                Value=value,
                Type='SecureString',
                Overwrite=True,
                Description=f"Environment variable for Posso ReAct Agent: {env_var}"
            )
            
            logger.info(f"✅ {param_path} - success")
            success_count += 1
            
        except Exception as e:
            logger.error(f"❌ {param_path} - failed: {e}")
    
    logger.info(f"\n🎉 Summary:")
    logger.info(f"   ✅ Success: {success_count}")
    logger.info(f"   ⚠️  Skipped: {skip_count}")
    logger.info(f"   📍 Region: {region}")
    
    if success_count > 0:
        logger.info(f"\n🚀 Ready to deploy with: serverless deploy --region {region}")

def list_parameters(region='ap-southeast-1'):
    """List all /posso/* parameters"""
    ssm = boto3.client('ssm', region_name=region)
    
    try:
        response = ssm.get_parameters_by_path(
            Path='/posso/',
            Recursive=True,
            WithDecryption=False  # Don't show values for security
        )
        
        logger.info(f"📋 Current parameters in {region}:")
        for param in response['Parameters']:
            logger.info(f"   {param['Name']} ({param['Type']})")
            
    except Exception as e:
        logger.error(f"Failed to list parameters: {e}")

def main():
    """Main function"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Manage AWS Parameter Store for Posso ReAct Agent')
    parser.add_argument('--region', default='ap-southeast-1', help='AWS region')
    parser.add_argument('--list', action='store_true', help='List existing parameters')
    parser.add_argument('--upload', action='store_true', help='Upload .env to Parameter Store')
    
    args = parser.parse_args()
    
    if args.list:
        list_parameters(args.region)
    elif args.upload:
        upload_env_to_parameter_store(args.region)
    else:
        # Default: upload
        upload_env_to_parameter_store(args.region)

if __name__ == "__main__":
    main()