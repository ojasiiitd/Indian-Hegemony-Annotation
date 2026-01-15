import json
from google import genai
from google.genai import types
from config import API_KEYS_PATH

with open(API_KEYS_PATH, "r") as f:
    API_KEY = json.load(f)["GEMINI_API_KEY"]

_client = genai.Client(api_key=API_KEY)

def generate_llm_output(prompt: str) -> str:
    response = _client.models.generate_content(
        model="gemini-3-flash-preview",
        contents=[prompt],
        config=types.GenerateContentConfig(
            system_instruction="Answer in 100-200 words.",
            temperature=0.2
        )
    )
    return response.text