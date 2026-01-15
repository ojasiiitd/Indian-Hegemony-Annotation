import json
from google import genai
from google.genai import types
from config import API_KEYS_PATH

with open(API_KEYS_PATH, "r") as f:
    keys = json.load(f)

# -------- GEMINI --------
_gemini_client = genai.Client(api_key=keys["GEMINI_API_KEY"])

# def generate_gemini_output(prompt: str) -> str:
#     response = _gemini_client.models.generate_content(
#         model="gemini-3-flash-preview",
#         contents=[prompt],
#         config=types.GenerateContentConfig(
#             system_instruction="Answer in 100-200 words.",
#             temperature=0.2
#         )
#     )
#     return response.text
def generate_gemini_output(prompt: str) -> str:
    """
    Placeholder.
    Replace with Gemini later.
    """
    return f"[GEMINI output placeholder]\n\n{prompt}"


def generate_llama_output(prompt: str) -> str:
    """
    Placeholder.
    Replace with LLAMA later.
    """
    return f"[LLAMA output placeholder]\n\n{prompt}"


# -------- CHATGPT (stub / replace later) --------
def generate_chatgpt_output(prompt: str) -> str:
    """
    Placeholder.
    Replace with OpenAI later.
    """
    return f"[ChatGPT output placeholder]\n\n{prompt}"