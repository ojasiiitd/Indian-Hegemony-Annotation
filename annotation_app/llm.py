import json
from google import genai
from google.genai import types
from config import KEYS


# -------- GEMINI --------
_gemini_client = genai.Client(api_key=KEYS["GEMINI_API_KEY"])

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
    return f"[Model1 output placeholder]\n\n{prompt}"


def generate_llama_output(prompt: str) -> str:
    """
    Placeholder.
    Replace with LLAMA later.
    """
    return f"[Model3 output placeholder]\n\n{prompt}"


# -------- CHATGPT (stub / replace later) --------
def generate_gpt_output(prompt: str) -> str:
    """
    Placeholder.
    Replace with OpenAI later.
    """
    return f"[Model2 output placeholder]\n\n{prompt}"

def generate_deepseek_output(prompt: str) -> str:
    """
    Placeholder.
    Replace with Deepseek later.
    """
    return f"[Model4 output placeholder]\n\n{prompt}"