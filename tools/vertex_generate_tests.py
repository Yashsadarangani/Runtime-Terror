import os
import sys
import argparse
import subprocess
import re
from pathlib import Path

from vertexai import init
from vertexai.generative_models import GenerativeModel


def validate_java_syntax(java_code):
    """Validate Java syntax by checking brace balance and basic structure"""

    if not re.search(r'(class|interface|enum)\s+\w+', java_code):
        return False, "No class/interface/enum declaration found"

    open_braces = java_code.count('{')
    close_braces = java_code.count('}')

    if open_braces != close_braces:
        return False, f"Brace mismatch: {open_braces} opening, {close_braces} closing"

    lines = java_code.split('\n')
    in_class = False
    brace_level = 0

    for i, line in enumerate(lines):
        stripped = line.strip()
        if not stripped or stripped.startswith('//') or stripped.startswith('/*') or stripped.startswith('*'):
            continue

        brace_level += line.count('{') - line.count('}')

        if re.match(r'\s*(public\s+)?(class|interface|enum)', stripped):
            in_class = True

        if not in_class and brace_level == 0:
            if (re.match(r'\s*@\w+', stripped) or
                re.match(r'\s*(public|private|protected)', stripped) or
                re.match(r'\s*\w+.*\(.*\).*\{', stripped)):
                return False, f"Code outside class at line {i+1}: {stripped}"

    return True, "Valid"


def fix_common_issues(java_code):
    """Fix common issues in generated code"""

    if 'import org.junit.jupiter.api.Test;' not in java_code:
        java_code = add_missing_imports(java_code)

    open_braces = java_code.count('{')
    close_braces = java_code.count('}')

    if open_braces > close_braces:
        missing_braces = open_braces - close_braces
        java_code += '\n' + ('}' * missing_braces)

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


def call_vertex_ai_api(prompt, project_id="runtime-terror-473009"):
    """Call Vertex AI Gemini and return generated Java test code"""
    try:
        init(project=project_id, location="us-central1")
        model = GenerativeModel("gemini-2.5-pro")

        response = model.generate_content(
            prompt,
            generation_config={
                "temperature": 0.2,
                "top_p": 0.8,
                "max_output_tokens": 40960,
            },
        )

        if response and response.candidates:
            for part in response.candidates[0].content.parts:
                if hasattr(part, "text") and part.text:
                    return part.text.strip()

        raise ValueError("Vertex AI did not return any text")
    except Exception as e:
        raise RuntimeError(f"Vertex AI call failed: {str(e)}")


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
Generate a comprehensive JUnit 5 test class for the following Java service class.

Requirements:
1. Use JUnit 5 annotations (@Test, @BeforeEach, etc.)
2. Use Mockito for mocking dependencies (@Mock, @InjectMocks)
3. Include @ExtendWith(MockitoExtension.class)
4. Test all public methods
5. Include positive and negative test cases
6. Use proper assertions (assertEquals, assertThrows, etc.)
7. Ensure the class is properly structured with complete closing braces
8. Include proper package declaration and imports

Source code to test:
{source_code}

Generate ONLY the complete test class with proper structure.
Class name should be: {test_class_name}
"""

    generated_code = call_vertex_ai_api(prompt, project_id)

    is_valid, message = validate_java_syntax(generated_code)

    if not is_valid:
        print(f"Generated code validation failed: {message}")
        print("Attempting to fix...")
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

    java_files = list(source_dir.glob('**/*.java'))

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

            print(f"✅ Generated test: {test_output_path}")

            compile_success, compile_message = compile_test_java(test_output_path)
            if not compile_success:
                print(f"⚠️ WARNING: Generated test may have issues: {compile_message}")

        except Exception as e:
            print(f"❌ Failed to generate test for {java_file}: {str(e)}")
            continue


if __name__ == '__main__':
    main()
