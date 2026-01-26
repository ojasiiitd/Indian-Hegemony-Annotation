import json
from google import genai
from google.genai import types
from config import KEYS
from openai import OpenAI


_gemini_client = genai.Client(api_key=KEYS["GEMINI_API_KEY"])
_gpt_client = OpenAI(api_key=KEYS["GPT_API_KEY"])
# _llama_client = 
_deepseek_client =  OpenAI(api_key=KEYS["DEEPSEEK_API_KEY"], base_url="https://api.deepseek.com")

# def generate_gemini_output(prompt: str) -> str:
#     """
#     Placeholder.
#     """
#     return f"[Model1 output placeholder]\n\n{prompt}"
def generate_gemini_output(prompt: str) -> str:
    """
    Gemini Output Generator
    """
    response = _gemini_client.models.generate_content(
        model="gemini-3-flash-preview",
        contents=[prompt],
        config=types.GenerateContentConfig(
            system_instruction="Answer in 100-200 words.",
            temperature=0.8
        )
    )
    return response.text


def generate_llama_output(prompt: str) -> str:
    """
    Placeholder.
    Replace with LLAMA later.
    """
    return f"[Model3 output placeholder]\n\n{prompt}"


# def generate_gpt_output(prompt: str) -> str:
#     """
#     Placeholder.
#     """
#     return f"[Model2 output placeholder]\n\n{prompt}"
def generate_gpt_output(prompt: str) -> str:
    """
    GPT5.2 Output Generator
    """
    response = _gpt_client.responses.create(
        model="gpt-5.2",
        reasoning={
            "effort": "low"
        },
        instructions= "Answer in 100-200 words.",
        input=prompt
    )

    return response.output_text


# def generate_deepseek_output(prompt: str) -> str:
#     """
#     Placeholder.
#     """
#     return f"[Model4 output placeholder]\n\n{prompt}"
def generate_deepseek_output(prompt: str) -> str:
    """
    DeepSeek Output Generator
    """

    response = _deepseek_client.chat.completions.create(
        model="deepseek-chat",
        thinking="disabled"
        messages=[
            {"role": "system", "content": "You are a helpful assistant"},
            {"role": "user", "content": f"{prompt}"},
        ],
        stream=False
    )

    print(response.choices[0].message.content)