import os
import argparse
from google.cloud import aiplatform
# 1. Import the correct class for generative models
from google.cloud.aiplatform.generative_models import GenerativeModel

# The location for Gemini models is us-central1
LOCATION = "us-central1"
# The name of the model you want to use
MODEL = "gemini-2.5-flash" # Using gemini-1.0-pro as it's a stable choice. You can change back to gemini-1.5-flash if you prefer.

aiplatform.init(location=LOCATION)

# 2. Instantiate the GenerativeModel class
model = GenerativeModel(MODEL)

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