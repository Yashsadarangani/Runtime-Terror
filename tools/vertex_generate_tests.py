import os
import re
import argparse
from pathlib import Path

from google.cloud import aiplatform
from vertexai import generative_models


# ---------------------------
# Vertex AI API Call
# ---------------------------
def call_vertex_ai_api(prompt, project_id="runtime-terror-473009"):
    """Call Vertex AI Gemini and return generated Java test code"""
    try:
        # Init Vertex AI
        aiplatform.init(project=project_id, location="us-central1")

        # Use Gemini Pro
        model = generative_models.GenerativeModel("gemini-1.5-pro")

        # Generate response
        response = model.generate_content(prompt)

        # Extract text
        if response and response.candidates:
            for part in response.candidates[0].content.parts:
                if hasattr(part, "text") and part.text:
                    return part.text.strip()

        raise ValueError("Vertex AI did not return any text")
    except Exception as e:
        raise RuntimeError(f"Vertex AI call failed: {str(e)}")


# ---------------------------
# Sanity Fixes for Test Code
# ---------------------------
def fix_common_issues(test_code: str) -> str:
    """Fix common Gemini test issues so code compiles"""
    imports = []
    if "import org.junit.jupiter.api.Test;" not in test_code:
        imports.append("import org.junit.jupiter.api.Test;")
    if "import org.junit.jupiter.api.Assertions;" not in test_code and "Assertions." in test_code:
        imports.append("import org.junit.jupiter.api.Assertions;")
    if "SpringBootTest" in test_code and "import org.springframework.boot.test.context.SpringBootTest;" not in test_code:
        imports.append("import org.springframework.boot.test.context.SpringBootTest;")

    if imports:
        # Insert imports after package declaration
        lines = test_code.splitlines()
        for i, line in enumerate(lines):
            if line.startswith("package "):
                lines.insert(i + 1, "\n".join(imports))
                break
        test_code = "\n".join(lines)

    return test_code


# ---------------------------
# Java Syntax Validation
# ---------------------------
def validate_java_syntax(code: str) -> bool:
    """Naive check to see if code looks like valid Java"""
    return "class " in code and "@Test" in code


# ---------------------------
# Generate Tests
# ---------------------------
def generate_test_with_vertex_ai(java_file: Path, output_dir: Path):
    """Generate unit test for a given Java service file"""
    try:
        source_code = java_file.read_text(encoding="utf-8")
        class_name = java_file.stem
        test_class_name = f"{class_name}Test"

        prompt = f"""
        You are a senior Java developer.
        Write a complete JUnit 5 unit test class for the following Spring Boot service:
        Class name: {class_name}
        Source code:
        {source_code}

        Requirements:
        - Use JUnit 5 annotations (@Test, @BeforeEach).
        - Use org.junit.jupiter.api.Assertions for assertions.
        - If Spring beans are used, annotate with @SpringBootTest.
        - The test class must be named {test_class_name}.
        - The package should match the original package, but end with .service.
        - Only return valid Java code, no explanations.
        """

        print(f"Generating test for {java_file}")
        test_code = call_vertex_ai_api(prompt)

        if not validate_java_syntax(test_code):
            print(f"WARNING: Generated test for {class_name} may be invalid, applying fixes")
            test_code = fix_common_issues(test_code)

        # Write test file
        output_dir.mkdir(parents=True, exist_ok=True)
        test_file = output_dir / f"{test_class_name}.java"
        test_file.write_text(test_code, encoding="utf-8")
        print(f"✅ Test written to {test_file}")

    except Exception as e:
        print(f"❌ Failed to generate test for {java_file}: {str(e)}")


# ---------------------------
# Main
# ---------------------------
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-dir", required=True, help="Path to Java source directory")
    parser.add_argument("--output-dir", required=True, help="Path to output test directory")
    parser.add_argument("--project-id", required=True, help="Google Cloud Project ID")
    args = parser.parse_args()

    source_dir = Path(args.source_dir)
    output_dir = Path(args.output_dir)

    # Find all services
    service_files = list(source_dir.glob("*.java"))
    for java_file in service_files:
        generate_test_with_vertex_ai(java_file, output_dir)


if _name_ == "_main_":
    main()
