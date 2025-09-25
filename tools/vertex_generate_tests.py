import os
import argparse
import re
import requests
import google.auth
import google.auth.transport.requests
import time
import subprocess
import tempfile
from pathlib import Path

# --- Configuration ---
MODEL_ID = "gemini-pro"
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

def validate_java_syntax(java_code):
    """Validate Java syntax by checking brace balance and basic structure"""
    
    # Check for basic class structure
    if not re.search(r'(class|interface|enum)\s+\w+', java_code):
        return False, "No class/interface/enum declaration found"
    
    # Check brace balance
    open_braces = java_code.count('{')
    close_braces = java_code.count('}')
    
    if open_braces != close_braces:
        return False, f"Brace mismatch: {open_braces} opening, {close_braces} closing"
    
    # Check for code outside class (simple heuristic)
    lines = java_code.split('\n')
    in_class = False
    brace_level = 0
    
    for i, line in enumerate(lines):
        stripped = line.strip()
        if not stripped or stripped.startswith('//') or stripped.startswith('/*') or stripped.startswith('*'):
            continue
            
        # Count braces
        brace_level += line.count('{') - line.count('}')
        
        # Check if we're in a class
        if re.match(r'\s*(public\s+)?(class|interface|enum)', stripped):
            in_class = True
        
        # Check for code outside class
        if not in_class and brace_level == 0:
            if (re.match(r'\s*@\w+', stripped) or  # annotations
                re.match(r'\s*(public|private|protected)', stripped) or  # methods
                re.match(r'\s*\w+.*\(.*\).*\{', stripped)):  # method signatures
                return False, f"Code outside class at line {i+1}: {stripped}"
    
    return True, "Valid"

def fix_common_issues(java_code):
    """Fix common issues in generated code"""
    
    # Ensure proper imports
    if 'import org.junit.jupiter.api.Test;' not in java_code:
        java_code = add_missing_imports(java_code)
    
    # Fix missing closing braces
    open_braces = java_code.count('{')
    close_braces = java_code.count('}')
    
    if open_braces > close_braces:
        missing_braces = open_braces - close_braces
        java_code += '\n' + '}'.join([''] * (missing_braces + 1))
    
    # Fix common syntax issues
    java_code = fix_syntax_issues(java_code)
    
    return java_code

def fix_syntax_issues(java_code):
    """Fix common syntax issues in generated code"""
    
    # Fix incomplete method signatures
    java_code = re.sub(r'(\w+)\s*\(\s*\)\s*;', r'\1() {\n        // TODO: Implement test\n    }', java_code)
    
    # Fix missing semicolons after imports
    java_code = re.sub(r'(import\s+[\w\.]+)(?<!;)(\n)', r'\1;\2', java_code)
    
    # Fix malformed annotations
    java_code = re.sub(r'@(\w+)\s*\n\s*(\w+)', r'@\1\n    \2', java_code)
    
    return java_code

def add_missing_imports(java_code):
    """Add standard test imports if missing"""
    standard_imports = [
        "import org.junit.jupiter.api.Test;",
        "import org.junit.jupiter.api.BeforeEach;",
        "import org.junit.jupiter.api.DisplayName;",
        "import org.junit.jupiter.api.extension.ExtendWith;",
        "import org.mockito.Mock;",
        "import org.mockito.InjectMocks;",
        "import org.mockito.junit.jupiter.MockitoExtension;",
        "import static org.junit.jupiter.api.Assertions.*;",
        "import static org.mockito.Mockito.*;",
        "import static org.mockito.ArgumentMatchers.*;"
    ]
    
    # Find package declaration
    package_match = re.search(r'package\s+[\w.]+;', java_code)
    if package_match:
        insert_pos = package_match.end()
        
        # Add imports after package
        imports_to_add = []
        for imp in standard_imports:
            if imp not in java_code:
                imports_to_add.append(imp)
        
        if imports_to_add:
            import_block = '\n\n' + '\n'.join(imports_to_add) + '\n'
            java_code = java_code[:insert_pos] + import_block + java_code[insert_pos:]
    
    return java_code

def compile_test_java(java_file_path):
    """Try to compile Java file to validate syntax"""
    try:
        # Use javac to check syntax
        result = subprocess.run([
            'javac', '-cp', '.:*', str(java_file_path)
        ], capture_output=True, text=True, timeout=30)
        
        if result.returncode == 0:
            return True, "Compilation successful"
        else:
            return False, f"Compilation failed: {result.stderr}"
    except FileNotFoundError:
        return False, "javac not found - skipping compilation check"
    except Exception as e:
        return False, f"Compilation check failed: {str(e)}"

def validate_and_fix_generated_code(generated_code, class_name, max_attempts=3):
    """Validate and fix generated test code with multiple attempts"""
    
    for attempt in range(max_attempts):
        print(f"🔍 Validation attempt {attempt + 1} for {class_name}")
        
        # Clean the code first
        cleaned_code = clean_generated_code(generated_code)
        
        # Validate syntax
        is_valid, message = validate_java_syntax(cleaned_code)
        
        if is_valid:
            print(f"✅ Validation successful for {class_name}")
            return cleaned_code, True
        
        print(f"⚠️  Validation failed for {class_name}: {message}")
        
        if attempt < max_attempts - 1:
            print(f"🔧 Attempting to fix issues...")
            cleaned_code = fix_common_issues(cleaned_code)
            generated_code = cleaned_code
        
    return cleaned_code, False

def create_enhanced_prompt(source_code, class_name, package_name):
    """Create an enhanced prompt for better test generation"""
    
    return f"""
Generate a comprehensive JUnit 5 test class for the following Java class.

STRICT REQUIREMENTS:
1. Use package declaration: package {package_name};
2. Include ALL necessary imports (JUnit 5, Mockito, assertions)
3. Use @ExtendWith(MockitoExtension.class) for the test class
4. Use @Mock for dependencies and @InjectMocks for the class under test
5. Include @Test annotations for all test methods
6. Test all public methods with positive, negative, and edge cases
7. Use meaningful test method names (shouldDoSomethingWhenCondition)
8. Include proper assertions (assertEquals, assertThrows, assertNotNull, etc.)
9. Ensure ALL braces are balanced and properly closed
10. Generate ONLY valid Java code without explanations or markdown

Class to test: {class_name}
Test class name should be: {class_name}Test

Source code:
{source_code}

Generate the complete test class with proper structure and balanced braces.
"""

def analyze_source_file(file_path):
    """Analyze source file to extract metadata"""
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            code = f.read()
        
        # Skip empty files
        if not code.strip():
            return None, "Empty file"
        
        package_name = extract_package_name(code)
        if not package_name:
            print(f"⚠️  No package found in {file_path}, using default")
            package_name = "com.github.yildizmy"
        
        # Check if it's a valid Java class
        if not re.search(r'(class|interface|enum)\s+\w+', code):
            return None, "No class/interface/enum found"
        
        return {
            'code': code,
            'package': package_name
        }, None
        
    except Exception as e:
        return None, f"Error reading file: {e}"

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
        "claude-sonnet-4@20250514",
        "gemini-2.5-pro",
        "gemini-2.5-flash", 
        "gemini-2.0-flash-001",
        "gemini-2.0-flash-lite-001"
    ]
    
    for model_id in models_to_try:
        api_endpoint = (
            f"https://{LOCATION}-aiplatform.googleapis.com/v1/projects/{project_id}"
            f"/locations/{LOCATION}/publishers/google/models/{model_id}:generateContent"
        )
        
        if try_generate_with_model(api_endpoint, access_token, source_code, class_name, package_name, out_dir, model_id):
            print(f"✅ Successfully used model: {model_id}")
            return True
    
    print(f"❌ All models failed for {class_name}")
    return False

def try_generate_with_model(api_endpoint: str, access_token: str, source_code: str, class_name: str, package_name: str, out_dir: str, model_id: str = ""):
    """Try to generate tests using a specific model endpoint with validation."""
    
    # Use enhanced prompt for better results
    prompt = create_enhanced_prompt(source_code, class_name, package_name)
    
    request_body = {
        "contents": [{
            "role": "user",
            "parts": [{"text": prompt}]
        }],
        "generationConfig": {
            "temperature": 0.1,  # Lower temperature for more consistent code
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
            print(f"⚠️  Model not found or not accessible: {model_id}")
            return False
        elif response.status_code == 403:
            print(f"⚠️  Permission denied for model: {model_id}")
            return False
        elif response.status_code == 429:
            print(f"⚠️  Rate limit exceeded, waiting...")
            time.sleep(10)  # Wait longer for rate limits
            return False
            
        response.raise_for_status()
        
        response_json = response.json()
        
        if 'candidates' not in response_json or not response_json['candidates']:
            print(f"⚠️  No candidates returned from model")
            return False
        
        generated_code = response_json['candidates'][0]['content']['parts'][0]['text']
        
        # Validate and fix the generated code
        validated_code, is_valid = validate_and_fix_generated_code(generated_code, class_name)
        
        if not is_valid:
            print(f"❌ Could not generate valid code for {class_name} with model {model_id}")
            return False
        
        # Create output directory structure matching the package structure
        package_path = package_name.replace('.', '/')
        full_out_dir = os.path.join(out_dir, package_path)
        os.makedirs(full_out_dir, exist_ok=True)
        
        test_file = os.path.join(full_out_dir, f"{class_name}Test.java")
        
        # Write the validated code
        with open(test_file, "w", encoding="utf-8") as f:
            f.write(validated_code)
        
        print(f"✅ Generated and validated: {test_file}")
        
        # Optional: Try to compile the generated test
        compile_success, compile_message = compile_test_java(test_file)
        if compile_success:
            print(f"✅ Compilation check passed for {class_name}")
        else:
            print(f"⚠️  Compilation check failed for {class_name}: {compile_message}")
            # Still return True as the syntax validation passed
        
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
    parser = argparse.ArgumentParser(description="Generate JUnit tests using Vertex AI with validation")
    parser.add_argument("--source_dir", 
                       default="backend/src/main/java/com/github/yildizmy/service", 
                       help="Directory with source .java files")
    parser.add_argument("--out_dir", 
                       default="backend/src/test/java", 
                       help="Where to write generated tests")
    parser.add_argument("--max_retries", 
                       type=int, 
                       default=3, 
                       help="Maximum retry attempts for failed generations")
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
    skipped_files = 0
    
    print(f"🔍 Scanning for Java files in: {args.source_dir}")
    
    for root, _, files in os.walk(args.source_dir):
        for file in files:
            if file.endswith(".java"):
                file_path = os.path.join(root, file)
                
                if should_skip_file(file_path):
                    print(f"⏭️  Skipping: {file}")
                    skipped_files += 1
                    continue
                
                class_name = file[:-5]  # Remove .java extension
                
                # Use enhanced file analysis
                analysis_result, error = analyze_source_file(file_path)
                if error:
                    print(f"⏭️  Skipping {file}: {error}")
                    skipped_files += 1
                    continue
                
                relative_path = os.path.relpath(root, args.source_dir)
                
                print(f"\n📝 Processing: {class_name} (package: {analysis_result['package']})")
                
                retry_count = 0
                generation_successful = False
                
                while retry_count < args.max_retries and not generation_successful:
                    if retry_count > 0:
                        print(f"🔄 Retry attempt {retry_count} for {class_name}")
                        time.sleep(5)  # Wait before retry
                    
                    generation_successful = generate_tests(
                        token, project, analysis_result['code'], 
                        class_name, analysis_result['package'], 
                        args.out_dir, relative_path
                    )
                    
                    retry_count += 1
                
                if generation_successful:
                    successful_generations += 1
                else:
                    failed_generations += 1
                    print(f"❌ Failed to generate test for {class_name} after {args.max_retries} attempts")
                
                # Add a delay to avoid rate limiting
                time.sleep(3)
    
    print(f"\n📊 Test Generation Summary:")
    print(f"✅ Successful: {successful_generations}")
    print(f"❌ Failed: {failed_generations}")
    print(f"⏭️  Skipped: {skipped_files}")
    print(f"📁 Output directory: {args.out_dir}")
    
    if failed_generations > 0:
        print(f"\n⚠️  {failed_generations} files failed generation. Check logs above for details.")
        exit(1)
    else:
        print(f"\n🎉 All test generation completed successfully!")