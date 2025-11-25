import google.generativeai as genai
import os

# Set your Gemini API key here or use environment variable
API_KEY = os.environ.get("GEMINI_API_KEY") or "YOUR_API_KEY_HERE"

genai.configure(api_key=API_KEY)

model = genai.GenerativeModel("models/gemini-2.5-pro")
prompt = """
You are an expert evaluator. Using the rubric below, score the staff member's activity (1-10) and provide a brief justification. Return your answer as JSON in this format:

{"score": 1-10, "justification": "..."}

Rubric:
Accountability: Demonstrates responsibility.

Activity:
Helped a student resolve a housing issue in a timely and professional manner.

Return only the JSON.
"""

generation_config = {
    "max_output_tokens": 256,
    "temperature": 0.3
}

try:
    response = model.generate_content(prompt, generation_config=generation_config)
    text = None
    if hasattr(response, 'text') and response.text:
        text = response.text
    elif hasattr(response, 'candidates') and response.candidates:
        for cand in response.candidates:
            if hasattr(cand, 'content') and cand.content and hasattr(cand.content, 'parts'):
                for part in cand.content.parts:
                    if hasattr(part, 'text') and part.text:
                        text = part.text
                        break
    if not text:
        print("No valid text in Gemini response.")
        print(f"Full response: {response}")
        finish_reason = getattr(response, 'finish_reason', None)
        if hasattr(response, 'candidates') and response.candidates:
            for cand in response.candidates:
                print(f"Candidate finish_reason: {getattr(cand, 'finish_reason', None)}")
        else:
            print(f"Response finish_reason: {finish_reason}")
    else:
        print("Gemini response:")
        print(text)
except Exception as e:
    print(f"Gemini scoring error: {e}")
