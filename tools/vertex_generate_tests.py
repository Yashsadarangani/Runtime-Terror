import os
import argparse
from google.cloud import aiplatform

from vertexai.generative_models import GenerativeModel

model = GenerativeModel("gemini-1.5-flash") 
# 1. Import the correct class for generative models
PROJECT_ID = "runtime-terror-473009"
LOCATION = "us-central1"


aiplatform.init(project=PROJECT_ID, location=LOCATION)



def generate_tests(source_code: str, class_name: str, out_dir: str):
    prompt = f"""
    You are an expert Java developer. Write JUnit 5 test cases 
    with meaningful assertions and edge cases for this class. Provide only the pure Java code, without any introductory text, explanations, or markdown formatting.

    {source_code}
    """
    # 3. Use the .generate_content() method
    response = model.generate_content(prompt)

    # 4. Access the generated code via the .text attribute
    test_code = response.text

    os.makedirs(out_dir, exist_ok=True)
    test_file = os.path.join(out_dir, f"{class_name}Test.java")
    with open(test_file, "w", encoding="utf-8") as f:
        f.write(test_code)
    print(f"✅ Generated: {test_file}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--source_dir",
        default="backend/src/main/java/com/github/yildizmy",
        help="Directory with source .java files"
    )
    parser.add_argument(
        "--out_dir",
        default="src/test/java/generated_tests",
        help="Where to write generated tests"
    )
    args = parser.parse_args()

    for root, _, files in os.walk(args.source_dir):
        for file in files:
            if file.endswith(".java"):
                class_name = file[:-5]  # drop .java
                with open(os.path.join(root, file), "r", encoding="utf-8") as f:
                    code = f.read()
                print(f"Generating tests for: {class_name}")
                generate_tests(code, class_name, args.out_dir)
