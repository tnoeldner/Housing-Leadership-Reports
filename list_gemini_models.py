from google import genai

def list_models():
    client = genai.Client()
    models = client.models.list()
    print("Available Gemini models:")
    for model in models:
        print(f"- {model.name}")

if __name__ == "__main__":
    list_models()