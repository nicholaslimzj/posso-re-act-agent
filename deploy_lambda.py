#!/usr/bin/env python3
"""
Deploy Posso ReAct Agent to AWS Lambda with SnapStart
"""

import boto3
import zipfile
import os
import json
from pathlib import Path
import subprocess
import tempfile
import shutil

def create_lambda_package():
    """Create Lambda deployment package"""
    print("📦 Creating Lambda deployment package...")
    
    # Create temporary directory
    with tempfile.TemporaryDirectory() as temp_dir:
        package_dir = Path(temp_dir) / "package"
        package_dir.mkdir()
        
        # Install dependencies
        print("Installing dependencies...")
        subprocess.run([
            "pip", "install", "-r", "lambda_requirements.txt", 
            "-t", str(package_dir)
        ], check=True)
        
        # Copy application code
        print("Copying application code...")
        files_to_copy = [
            "lambda_handler.py",
            "message_handler.py", 
            "config/",
            "context/",
            "agents/",
            "tools/",
            "models/",
            "integrations/",
            "data/"
        ]
        
        for item in files_to_copy:
            src = Path(item)
            if src.is_file():
                shutil.copy2(src, package_dir / src.name)
            elif src.is_dir():
                shutil.copytree(src, package_dir / src.name)
        
        # Create ZIP package
        zip_path = Path("posso-react-agent-lambda.zip")
        print(f"Creating ZIP package: {zip_path}")
        
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for root, dirs, files in os.walk(package_dir):
                for file in files:
                    file_path = Path(root) / file
                    arcname = file_path.relative_to(package_dir)
                    zipf.write(file_path, arcname)
        
        print(f"✅ Package created: {zip_path} ({zip_path.stat().st_size / 1024 / 1024:.1f} MB)")
        return zip_path

def deploy_lambda(zip_path: Path):
    """Deploy to AWS Lambda with SnapStart"""
    print("🚀 Deploying to AWS Lambda...")
    
    lambda_client = boto3.client('lambda')
    function_name = "posso-react-agent"
    
    # Function configuration
    config = {
        'FunctionName': function_name,
        'Runtime': 'python3.11',
        'Role': 'arn:aws:iam::YOUR_ACCOUNT:role/lambda-execution-role',  # Update this
        'Handler': 'lambda_handler.lambda_handler',
        'Timeout': 300,  # 5 minutes
        'MemorySize': 1024,
        'Environment': {
            'Variables': {
                'ENV': 'production'
                # Other env vars set via AWS CLI/Console for security
            }
        }
    }
    
    try:
        # Try to update existing function
        print("Updating existing function...")
        with open(zip_path, 'rb') as zip_file:
            lambda_client.update_function_code(
                FunctionName=function_name,
                ZipFile=zip_file.read()
            )
        
        # Update configuration
        lambda_client.update_function_configuration(**config)
        
    except lambda_client.exceptions.ResourceNotFoundException:
        # Create new function
        print("Creating new function...")
        with open(zip_path, 'rb') as zip_file:
            config['Code'] = {'ZipFile': zip_file.read()}
            lambda_client.create_function(**config)
    
    # Enable SnapStart
    print("🔥 Enabling SnapStart...")
    lambda_client.put_provisioned_concurrency_config(
        FunctionName=function_name,
        Qualifier='$LATEST',
        ProvisionedConcurrencyConfig={
            'ApplyOn': 'PublishedVersions'
        }
    )
    
    # Publish version for SnapStart
    version_response = lambda_client.publish_version(
        FunctionName=function_name,
        Description='SnapStart enabled version'
    )
    
    print(f"✅ Deployed version: {version_response['Version']}")
    
    # Create alias pointing to versioned function
    try:
        lambda_client.create_alias(
            FunctionName=function_name,
            Name='prod',
            FunctionVersion=version_response['Version']
        )
    except lambda_client.exceptions.ResourceConflictException:
        # Update existing alias
        lambda_client.update_alias(
            FunctionName=function_name,
            Name='prod',
            FunctionVersion=version_response['Version']
        )
    
    print("✅ Lambda deployment completed!")
    print(f"Function ARN: {version_response['FunctionArn']}")

def create_api_gateway():
    """Create API Gateway for webhook endpoint"""
    print("🌐 Setting up API Gateway...")
    
    apigw = boto3.client('apigateway')
    
    # This is a simplified example - you'd want to use CDK/CloudFormation
    # for production deployments
    
    print("⚠️  Manual step required:")
    print("1. Create API Gateway REST API")
    print("2. Create POST method on /webhook path")
    print("3. Integrate with Lambda function")
    print("4. Deploy API stage")
    print("5. Configure Chatwoot webhook URL")

def main():
    """Main deployment script"""
    print("🚀 Deploying Posso ReAct Agent to AWS Lambda with SnapStart")
    
    # Create package
    zip_path = create_lambda_package()
    
    # Deploy to Lambda
    deploy_lambda(zip_path)
    
    # Set up API Gateway
    create_api_gateway()
    
    print("🎉 Deployment complete!")
    print("Don't forget to:")
    print("1. Set environment variables in Lambda console")
    print("2. Update IAM role ARN in script")  
    print("3. Configure API Gateway webhook endpoint")

if __name__ == "__main__":
    main()