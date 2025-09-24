import os
import argparse
import json
import requests
import google.auth
import google.auth.transport.requests

# --- Configuration ---
# Use the model you prefer.
MODEL_ID = "gemini-2.5-flash"
# The region for your model.
LOCATION = "us-central1"

def get_access_token():
    """Gets the default access token to authenticate to the Google Cloud API."""
    # This automatically finds the credentials in the Cloud Build environment.
    credentials, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
    auth_request = google.auth.transport.requests.Request()
    credentials.refresh(auth_request)
    return credentials.token, credentials.project_id

def generate_tests(access_token: str, project_id: str, source_code: str, class_name: str, out_dir: str):
    """Generates tests by calling the Vertex AI REST API."""
    
    # Construct the API endpoint
    api_endpoint = (
        f"https://{LOCATION}-aiplatform.googleapis.com/v1/projects/{project_id}"
        f"/locations/{LOCATION}/publishers/google/models/{MODEL_ID}:generateContent"
    )

    # Prepare the prompt and request payload
    prompt = f"""
    You are an expert Java developer. Write JUnit 5 test cases 
    with meaningful assertions and edge cases for this class. Provide only the pure Java code, without any introductory text, explanations, or markdown formatting.

    {source_code}
    """
    
    request_body = {
        "contents": {
            "role": "user",
            "parts": [{"text": prompt}]
        }
    }

    # Set the headers for the request
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }

    # Make the POST request
    try:
        response = requests.post(api_endpoint, headers=headers, json=request_body, timeout=300)
        response.raise_for_status() # Raises an exception for bad status codes (4xx or 5xx)
        
        response_json = response.json()
        
        # Extract the generated code from the response
        test_code = response_json['candidates'][0]['content']['parts'][0]['text']

        os.makedirs(out_dir, exist_ok=True)
        test_file = os.path.join(out_dir, f"{class_name}Test.java")
        with open(test_file, "w", encoding="utf-8") as f:
            f.write(test_code)
        print(f"✅ Generated: {test_file}")

    except requests.exceptions.RequestException as e:
        print(f"❌ Error calling Vertex AI API: {e}")
        # If the response has content, print it for more detailed error info
        if e.response is not None:
            print(f"❌ Response Body: {e.response.text}")
        raise

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--source_dir", default="backend/src/main/java/com/github/yildizmy", help="Directory with source .java files")
    parser.add_argument("--out_dir", default="src/test/java/generated_tests", help="Where to write generated tests")
    args = parser.parse_args()

    print("Authenticating with Google Cloud...")
    token, project = get_access_token()
    print(f"Successfully authenticated for project: {project}")

    for root, _, files in os.walk(args.source_dir):
        for file in files:
            if file.endswith(".java"):
                class_name = file[:-5]
                with open(os.path.join(root, file), "r", encoding="utf-8") as f:
                    code = f.read()
                print(f"Generating tests for: {class_name}")
                generate_tests(token, project, code, class_name, args.out_dir)