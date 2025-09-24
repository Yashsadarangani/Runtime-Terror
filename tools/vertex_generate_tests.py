import os
import argparse
from google.cloud import aiplatform

PROJECT_ID = "runtime-terror-973009"
LOCATION = "us-central1"
MODEL = "models/gemini-flash-2.5"

aiplatform.init(project=PROJECT_ID, location=LOCATION)
model = aiplatform.Model(model_name=MODEL)

def generate_tests(source_code: str, class_name: str, out_dir: str):
    prompt = f"""
    You are an expert Java developer. Write JUnit 5 test cases 
    with meaningful assertions and edge cases for this class:

    {source_code}
    """
    response = model.predict(instances=[{"content": prompt}])
    test_code = response.predictions[0]

    os.makedirs(out_dir, exist_ok=True)
    test_file = os.path.join(out_dir, f"{class_name}Test.java")
    with open(test_file, "w", encoding="utf-8") as f:
        f.write(test_code)
    print(f"✅ Generated: {test_file}")


if _name_ == "_main_":
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
