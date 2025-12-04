import google.generativeai as genai
import os

def test_gemini():
    api_key = os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        print("Missing GOOGLE_API_KEY environment variable.")
        return
    try:
        genai.configure(api_key=api_key)
        print("Available models and supported methods:")
        for model_info in genai.list_models():
            print(model_info.name, model_info.supported_generation_methods)
        # Use a supported model name, e.g., 'gemini-pro'
        model = genai.GenerativeModel("gemini-pro")
        response = model.generate_content("Say hello")
        print("Gemini response:", getattr(response, "text", None))
    except Exception as e:
        import traceback
        print("Gemini test exception:", e)
        print(traceback.format_exc())

if __name__ == "__main__":
    test_gemini()
