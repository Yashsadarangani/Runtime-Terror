import os
import re
import argparse
from pathlib import Path
import subprocess

from google.cloud import aiplatform
from vertexai.generative_models import GenerativeModel


def validate_java_syntax(java_code):
    """Validate Java syntax by checking brace balance and basic structure"""
    if not re.search(r'(class|interface|enum)\s+\w+', java_code):
        return False, "No class/interface/enum declaration found"

    open_braces = java_code.count('{')
    close_braces = java_code.count('}')
    if open_braces != close_braces:
        return False, f"Brace mismatch: {open_braces} opening, {close_braces} closing"

    return True, "Valid"


def fix_common_issues(java_code):
    """Fix common issues in generated code"""
    if 'import org.junit.jupiter.api.Test;' not in java_code:
        java_code = add_missing_imports(java_code)

    open_braces = java_code.count('{')
    close_braces = java_code.count('}')
    if open_braces > close_braces:
        java_code += '\n' + '}' * (open_braces - close_braces)
    return java_code


def add_missing_imports(java_code):
    """Add standard test imports if missing"""
    standard_imports = [
        "import org.junit.jupiter.api.Test;",
        "import org.junit.jupiter.api.BeforeEach;",
        "import org.junit.jupiter.api.extension.ExtendWith;",
        "import org.mockito.Mock;",
        "import org.mockito.InjectMocks;",
        "import org.mockito.junit.jupiter.MockitoExtension;",
        "import static org.junit.jupiter.api.Assertions.*;",
        "import static org.mockito.Mockito.*;",
    ]
    package_match = re.search(r'package\s+[\w.]+;', java_code)
    if package_match:
        insert_pos = package_match.end()
        imports_to_add = [imp for imp in standard_imports if imp not in java_code]
        if imports_to_add:
            import_block = '\n\n' + '\n'.join(imports_to_add) + '\n'
            java_code = java_code[:insert_pos] + import_block + java_code[insert_pos:]
    return java_code


def compile_test_java(java_file_path):
    """Try to compile Java file to validate syntax"""
    try:
        result = subprocess.run(
            ['javac', '-cp', '.:*', str(java_file_path)],
            capture_output=True, text=True, timeout=30
        )
        if result.returncode == 0:
            return True, "Compilation successful"
        else:
            return False, f"Compilation failed: {result.stderr}"
    except Exception as e:
        return False, f"Compilation check failed: {str(e)}"


def call_vertex_ai_api(prompt, project_id):
    """Call Vertex AI Gemini to generate test code"""
    try:
        aiplatform.init(project=project_id, location="us-central1")
        model = GenerativeModel("gemini-1.5-pro")
        response = model.generate_content(prompt)
        if response and response.candidates:
            return response.candidates[0].content.parts[0].text.strip()
        else:
            raise ValueError("No response from Vertex AI")
    except Exception as e:
        raise RuntimeError(f"Vertex AI API failed: {str(e)}")


def generate_test_with_vertex_ai(source_file_path, project_id="runtime-terror-473009"):
    """Generate test using Vertex AI with validation"""
    with open(source_file_path, 'r') as f:
        source_code = f.read()

    class_match = re.search(r'class\s+(\w+)', source_code)
    if not class_match:
        raise ValueError(f"Could not find class name in {source_file_path}")

    class_name = class_match.group(1)
    test_class_name = f"{class_name}Test"

    prompt = f"""
Generate a JUnit 5 test class for the following Java class.

Requirements:
- Use JUnit 5 annotations (@Test, @BeforeEach, etc.)
- Use Mockito for mocking dependencies (@Mock, @InjectMocks)
- Include @ExtendWith(MockitoExtension.class)
- Test all public methods with positive and negative cases
- Ensure balanced braces and valid Java syntax
- Class name should be: {test_class_name}

Source code:
{source_code}
"""

    generated_code = call_vertex_ai_api(prompt, project_id)

    is_valid, message = validate_java_syntax(generated_code)
    if not is_valid:
        print(f"Validation failed: {message}, attempting fix...")
        generated_code = fix_common_issues(generated_code)
        is_valid, message = validate_java_syntax(generated_code)
        if not is_valid:
            raise ValueError(f"Could not fix generated code: {message}")

    return generated_code


def main():
    parser = argparse.ArgumentParser(description='Generate validated Java tests')
    parser.add_argument('--source_dir', required=True, help='Source directory')
    parser.add_argument('--out_dir', required=True, help='Output directory')
    parser.add_argument('--project_id', default='runtime-terror-473009', help='GCP Project ID')
    args = parser.parse_args()

    source_dir = Path(args.source_dir)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    java_files = list(source_dir.glob('*/.java'))
    for java_file in java_files:
        try:
            print(f"Generating test for {java_file}")
            test_code = generate_test_with_vertex_ai(java_file, args.project_id)

            relative_path = java_file.relative_to(source_dir)
            test_file_name = relative_path.stem + 'Test.java'
            test_output_path = out_dir / relative_path.parent / test_file_name
            test_output_path.parent.mkdir(parents=True, exist_ok=True)

            with open(test_output_path, 'w') as f:
                f.write(test_code)

            print(f"Generated test: {test_output_path}")
            compile_success, compile_message = compile_test_java(test_output_path)
            if not compile_success:
                print(f"WARNING: Compilation issues: {compile_message}")
        except Exception as e:
            print(f"Failed for {java_file}: {str(e)}")


if _name_ == '_main_':
    main()
