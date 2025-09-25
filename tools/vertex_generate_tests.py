import os
import argparse
import re
import requests
import google.auth
import google.auth.transport.requests
import time
from pathlib import Path

# --- Configuration ---
LOCATION = "us-central1"

def get_access_token():
    """Gets the default access token to authenticate to the Google Cloud API."""
    try:
        credentials, project = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
        auth_request = google.auth.transport.requests.Request()
        credentials.refresh(auth_request)
        
        # Get project ID from environment or credentials
        project_id = project or os.environ.get('GOOGLE_CLOUD_PROJECT', 'runtime-terror-473009')
        
        return credentials.token, project_id
    except Exception as e:
        print(f"❌ Authentication failed: {e}")
        raise

def clean_generated_code(code_text):
    """Clean the generated code by removing markdown formatting and extra text."""
    # Remove markdown code blocks
    code_text = re.sub(r'```java\n?', '', code_text)
    code_text = re.sub(r'```\n?', '', code_text)
    
    # Remove any introductory text before the first import or package statement
    lines = code_text.split('\n')
    start_idx = 0
    
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith('package ') or stripped.startswith('import ') or stripped.startswith('@') or stripped.startswith('public class'):
            start_idx = i
            break
    
    return '\n'.join(lines[start_idx:]).strip()

def extract_package_name(source_code):
    """Extract package name from source code."""
    match = re.search(r'package\s+([\w\.]+);', source_code)
    return match.group(1) if match else ""

def generate_tests(access_token: str, project_id: str, source_code: str, class_name: str, package_name: str, out_dir: str, relative_path: str):
    """Generates tests by calling the Vertex AI REST API."""
    
    # Updated with current available models
    models_to_try = [
        "gemini-2.5-pro",
        "qwen2.5",
        "gemini-2.5-flash",
        "gemini-2.0-flash-001"
    ]
    
    for model_id in models_to_try:
        api_endpoint = (
            f"https://{LOCATION}-aiplatform.googleapis.com/v1/projects/{project_id}"
            f"/locations/{LOCATION}/publishers/google/models/{model_id}:generateContent"
        )
        
        if try_generate_with_model(api_endpoint, access_token, source_code, class_name, package_name, out_dir):
            print(f"✅ Successfully used model: {model_id}")
            return True
    
    print(f"❌ All models failed for {class_name}")
    return False


def try_generate_with_model(api_endpoint: str, access_token: str, source_code: str, class_name: str, package_name: str, out_dir: str):
    """Try to generate tests using a specific model endpoint."""
    
    prompt = f"""
Generate comprehensive JUnit 5 test cases for the following Java class.
Requirements:
1. Use proper package declaration: package {package_name};
2. Include all necessary imports
3. Use @ExtendWith(MockitoExtension.class) for mocking
4. Test all public methods with positive, negative, and edge cases
5. Use meaningful test method names
6. Include proper assertions
7. Mock external dependencies
8. Provide only clean Java code without explanations or markdown

Source code:
{source_code}
"""
    
    request_body = {
        "contents": [{
            "role": "user",
            "parts": [{"text": prompt}]
        }],
        "generationConfig": {
            "temperature": 0.1,
            "topP": 0.8,
            "maxOutputTokens": 64000
        }
    }

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }

    try:
        response = requests.post(api_endpoint, headers=headers, json=request_body, timeout=180)
        
        # Enhanced error handling
        if response.status_code == 404:
            print(f"⚠️  Model not found or not accessible: {api_endpoint.split('/')[-1].split(':')[0]}")
            return False
        elif response.status_code == 403:
            print(f"⚠️  Permission denied for model: {api_endpoint.split('/')[-1].split(':')[0]}")
            return False
        elif response.status_code == 429:
            print(f"⚠️  Rate limit exceeded, waiting...")
            time.sleep(5)  # Wait longer for rate limits
            return False
            
        response.raise_for_status()
        
        response_json = response.json()
        
        if 'candidates' not in response_json or not response_json['candidates']:
            print(f"⚠️  No candidates returned from model")
            return False
        
        test_code = response_json['candidates'][0]['content']['parts'][0]['text']
        test_code = clean_generated_code(test_code)
        
        # Create output directory structure matching the package structure
        package_path = package_name.replace('.', '/')
        full_out_dir = os.path.join(out_dir, package_path)
        os.makedirs(full_out_dir, exist_ok=True)
        
        test_file = os.path.join(full_out_dir, f"{class_name}Test.java")
        
        with open(test_file, "w", encoding="utf-8") as f:
            f.write(test_code)
        
        print(f"✅ Generated: {test_file}")
        return True
        
    except requests.exceptions.RequestException as e:
        if hasattr(e, 'response') and e.response:
            if e.response.status_code == 404:
                return False  # Model not available, try next one
            print(f"❌ HTTP error {e.response.status_code} for {class_name}: {e.response.text}")
        else:
            print(f"❌ Network error for {class_name}: {e}")
        return False
    except Exception as e:
        print(f"❌ Unexpected error for {class_name}: {e}")
        return False


def should_skip_file(file_path):
    """Check if file should be skipped for test generation."""
    # Skip test files, interfaces, enums, and certain utility classes
    skip_patterns = [
        'Test.java',
        'Tests.java',
        'Application.java',
        'Config.java'
    ]
    
    filename = os.path.basename(file_path)
    return any(pattern in filename for pattern in skip_patterns)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate JUnit tests using Vertex AI")
    parser.add_argument("--source_dir", 
                       default="backend/src/main/java/com/github/yildizmy/service", 
                       help="Directory with source .java files")
    parser.add_argument("--out_dir", 
                       default="backend/src/test/java", 
                       help="Where to write generated tests")
    args = parser.parse_args()

    print("🔐 Authenticating with Google Cloud...")
    try:
        token, project = get_access_token()
        print(f"✅ Successfully authenticated for project: {project}")
    except Exception as e:
        print(f"❌ Authentication failed: {e}")
        exit(1)

    # Ensure source directory exists
    if not os.path.exists(args.source_dir):
        print(f"❌ Source directory does not exist: {args.source_dir}")
        exit(1)

    successful_generations = 0
    failed_generations = 0
    
    print(f"🔍 Scanning for Java files in: {args.source_dir}")
    
    for root, _, files in os.walk(args.source_dir):
        for file in files:
            if file.endswith(".java"):
                file_path = os.path.join(root, file)
                
                if should_skip_file(file_path):
                    print(f"⏭️  Skipping: {file}")
                    continue
                
                class_name = file[:-5]  # Remove .java extension
                
                try:
                    with open(file_path, "r", encoding="utf-8") as f:
                        code = f.read()
                    
                    # Skip empty files
                    if not code.strip():
                        print(f"⏭️  Skipping empty file: {file}")
                        continue
                    
                    package_name = extract_package_name(code)
                    if not package_name:
                        print(f"⚠️  No package found in {file}, using default")
                        package_name = "com.github.yildizmy"
                    
                    relative_path = os.path.relpath(root, args.source_dir)
                    
                    print(f"📝 Processing: {class_name} (package: {package_name})")
                    
                    if generate_tests(token, project, code, class_name, package_name, args.out_dir, relative_path):
                        successful_generations += 1
                    else:
                        failed_generations += 1
                    
                    # Add a small delay to avoid rate limiting
                    time.sleep(2)
                    
                except Exception as e:
                    print(f"❌ Error processing {file}: {e}")
                    failed_generations += 1
    
    print(f"\n📊 Test Generation Summary:")
    print(f"✅ Successful: {successful_generations}")
    print(f"❌ Failed: {failed_generations}")
    print(f"📁 Output directory: {args.out_dir}")
    
    if failed_generations > 0:
        exit(1)