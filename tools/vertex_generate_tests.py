import os
import re
import argparse
from pathlib import Path
import subprocess

try:
    from google.cloud import aiplatform
    from vertexai.preview.language_models import TextGenerationModel
except ImportError:
    raise ImportError("Please install google-cloud-aiplatform and vertexai packages")


def validate_java_syntax(java_code):
    if not re.search(r'(class|interface|enum)\s+\w+', java_code):
        return False, "No class/interface/enum declaration found"
    if java_code.count('{') != java_code.count('}'):
        return False, f"Brace mismatch: {java_code.count('{')} opening, {java_code.count('}')} closing"
    return True, "Valid"


def add_missing_imports(java_code):
    imports = [
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
        imports_to_add = [i for i in imports if i not in java_code]
        java_code = java_code[:insert_pos] + '\n\n' + '\n'.join(imports_to_add) + '\n' + java_code[insert_pos:]
    return java_code


def fix_common_issues(java_code):
    if 'import org.junit.jupiter.api.Test;' not in java_code:
        java_code = add_missing_imports(java_code)
    if java_code.count('{') > java_code.count('}'):
        java_code += '\n' + '}' * (java_code.count('{') - java_code.count('}'))
    return java_code


def compile_test_java(java_file_path):
    try:
        result = subprocess.run(
            ['javac', '-cp', '.:*', str(java_file_path)],
            capture_output=True, text=True, timeout=30
        )
        return (result.returncode == 0, result.stderr)
    except Exception as e:
        return False, str(e)


def detect_private_fields(java_code):
    """Detect all private fields for automatic mocking"""
    pattern = r'private\s+([\w<>]+)\s+(\w+);'
    return re.findall(pattern, java_code)


def add_mocks_to_test(test_code, fields, class_name):
    """Add @Mock for private fields and @InjectMocks for the service class"""
    mocks = ""
    for field_type, field_name in fields:
        mocks += f"    @Mock\n    private {field_type} {field_name};\n"
    inject = f"    @InjectMocks\n    private {class_name} {class_name[0].lower() + class_name[1:]};\n"

    # Add @ExtendWith if not present
    if "@ExtendWith(MockitoExtension.class)" not in test_code:
        test_code = test_code.replace("public class", "@ExtendWith(MockitoExtension.class)\npublic class", 1)

    # Insert mocks at beginning of class body
    test_code = re.sub(r'public class \w+\s*{', lambda m: m.group(0) + '\n' + mocks + inject, test_code)
    return test_code


def call_vertex_ai_api(prompt, project_id):
    try:
        aiplatform.init(project=project_id, location="us-central1")
        model = TextGenerationModel.from_pretrained("gemini-1.5-pro")
        response = model.predict(prompt, max_output_tokens=16000)
        return response.text.strip()
    except Exception as e:
        raise RuntimeError(f"Vertex AI API failed: {str(e)}")


def generate_test_with_vertex_ai(source_file_path, project_id):
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
- Use JUnit 5 annotations (@Test, @BeforeEach)
- Use Mockito for dependencies
- Include positive & negative test cases
- Class name: {test_class_name}
- Ensure balanced braces

Source code:
{source_code}
"""

    generated_code = call_vertex_ai_api(prompt, project_id)
    generated_code = fix_common_issues(generated_code)

    # Detect private fields and add mocks
    private_fields = detect_private_fields(source_code)
    if private_fields:
        generated_code = add_mocks_to_test(generated_code, private_fields, class_name)

    return generated_code


def main():
    parser = argparse.ArgumentParser(description='Generate validated Java tests')
    parser.add_argument('--source_dir', required=True)
    parser.add_argument('--out_dir', required=True)
    parser.add_argument('--project_id', default='runtime-terror-473009')
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
            success, msg = compile_test_java(test_output_path)
            if not success:
                print(f"WARNING: Compilation issues: {msg}")

        except Exception as e:
            print(f"Failed for {java_file}: {e}")


if _name_ == '_main_':
    main()
