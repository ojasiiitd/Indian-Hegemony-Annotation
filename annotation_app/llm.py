import json
from google import genai
from google.genai import types
from config import KEYS
from openai import OpenAI
import requests

_gemini_client = genai.Client(api_key=KEYS["GEMINI_API_KEY"])
_gpt_client = OpenAI(api_key=KEYS["GPT_API_KEY"])
_deepseek_client =  OpenAI(api_key=KEYS["DEEPSEEK_API_KEY"], base_url="https://api.deepseek.com")


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

def generate_deepseek_output(prompt: str) -> str:
    """
    DeepSeek Output Generator
    """
    response = requests.post(
    url="https://openrouter.ai/api/v1/chat/completions",
    headers={
        "Authorization": f"Bearer {KEYS["OPENAI_API_KEY"]}",
        "Content-Type": "application/json",
    },
    data=json.dumps({
            "model": "deepseek/deepseek-v3.2",
            "messages": [
                {
                    "role": "system",
                    "content": "Answer in 100-200 words."
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            "reasoning": {"enabled": True}
        })
    )
    response = response.json()
    response = response['choices'][0]['message']['content']
    return response


def generate_llama_output(prompt: str) -> str:
    """
    GPT-OSS-120B Output Generator
    """
    response = requests.post(
    url="https://openrouter.ai/api/v1/chat/completions",
    headers={
        "Authorization": f"Bearer {KEYS["OPENAI_API_KEY"]}",
        "Content-Type": "application/json",
    },
    data=json.dumps({
        "model": "openai/gpt-oss-120b",
        "messages": [
                {
                    "role": "system",
                    "content": "Answer in 100-200 words."
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
        "reasoning": {"enabled": True}
    })
    )
    response = response.json()
    response = response['choices'][0]['message']['content']
    return response

